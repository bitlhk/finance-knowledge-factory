import copy
import json
import threading
import time
from urllib import request, error
from http.server import ThreadingHTTPServer

import pytest

from knowledge_core.contracts import Rejected
from web_production.engine import Production, parse, SAMPLE, digest, persist
from web_production.server import handler

HTML = '<html><body><p>第一条 用于个人消费的贷款期限不得超过五年。</p><p>第二条 还款事项待人工复核。</p></body></html>'


def response(payload):
    return {'model':'controlled-test-model', 'usage':None, 'choices':[{'finish_reason':'stop', 'message':{'content':json.dumps({
        'units':[{'id':'duration', 'kind':'CONDITION', 'quote':'用于个人消费的贷款期限不得超过五年',
                  'state':'PROPOSED_NUMERIC', 'branchQuote':'用于个人消费'}], 'relations':[]}, ensure_ascii=False)}}]}


def submit(p, rules=False, tests=None):
    src=p.source('合成制度',HTML)
    data=dict(requestId='request-test-123',sourceId=src['id'],rules=rules,
              clauses=['第一条'] if rules else [],tests=tests or [],modelConsent=rules)
    return p.submit(data),data


def done(p, job):
    for _ in range(100):
        row=p.get(job['id'])
        if row['status'] in {'COMPLETED','FAILED','PARTIAL'}:
            return row
        time.sleep(.03)
    raise AssertionError('Job did not finish')


def test_real_source_parsing_and_source_quotes():
    chunks=parse(SAMPLE.read_bytes())
    assert len(chunks)==52
    assert all(c['anchors'] for c in chunks)
    assert len(parse(HTML.encode()))==2
    with pytest.raises(Rejected): parse(b'<html><p>No numbered clauses</p></html>')
    with pytest.raises(Rejected): parse(('a'*1_000_001).encode())
    with pytest.raises(Rejected): parse(b'<html><p>')


def test_document_production_search_testset_and_restart(tmp_path):
    p=Production(tmp_path, caller=lambda _: pytest.fail('Document-only must not call model'))
    job,_=submit(p,tests=[{'question':'第一条','expectedClause':'第一条'}])
    result=done(p,job)
    assert result['status']=='COMPLETED'
    assert result['artifactDigest']==digest(result['artifact'])
    assert result['artifact']['validation']['retrievalTests'][0]['passed']
    assert not result['publicationAllowed'] and result['attempts']==[]
    search=p.search(job['id'],'第一条')
    assert search['hits'][0]['clause']=='第一条' and not search['generatedAnswer']
    p.close()
    restored=Production(tmp_path)
    assert restored.get(job['id'])['artifactDigest']==result['artifactDigest']
    assert restored.get(job['id'])['consumptionReceipts'][0]['id']==search['id']
    assert restored.search(job['id'],'不存在的zzzyyy')['hits']==[]
    restored.close()


def test_new_model_call_not_history_idempotency_and_conflict(tmp_path):
    calls=[]
    def caller(payload):
        calls.append(copy.deepcopy(payload))
        return response(payload)
    p=Production(tmp_path,caller=caller)
    job,data=submit(p,True)
    result=done(p,job)
    assert result['status']=='COMPLETED' and len(calls)==1
    assert p.submit(data)['id']==job['id'] and len(calls)==1
    with pytest.raises(Rejected,match='IDEMPOTENCY_CONFLICT'):
        p.submit({**data,'tests':[{'question':'第二条','expectedClause':'第二条'}]})
    r=result['artifact']['rules'][0]
    assert r['projection']['ir']['rules'] and r['compiled'] and r['binding']
    assert r['coverage']=='NOT_INDEPENDENTLY_ASSESSED'
    assert 'expected' not in json.dumps(calls[0])
    new=p.submit({**data,'requestId':'new-request-123'})
    done(p,new)
    assert new['id']!=job['id'] and len(calls)==2
    p.close()
    p=Production(tmp_path,caller=caller)
    assert p.submit(data)['id']==job['id'] and len(calls)==2
    p.close()


@pytest.mark.parametrize('bad', ['truncated','wrong_quote','exception','formula'])
def test_model_failure_preserves_document_outputs(tmp_path,bad):
    def caller(payload):
        if bad=='exception': raise TimeoutError()
        obj=response(payload)
        if bad=='truncated': obj['choices'][0]['finish_reason']='length'
        else:
            sem=json.loads(obj['choices'][0]['message']['content'])
            if bad=='wrong_quote': sem['units'][0]['quote']='凭空添加的条件'
            if bad=='formula': sem['units'][0]['predicate']={'op':'eq'}
            obj['choices'][0]['message']['content']=json.dumps(sem)
        return obj
    p=Production(tmp_path,caller=caller)
    job,_=submit(p,True)
    r=done(p,job)
    assert r['status']=='PARTIAL' and r['artifact']['rules']==[]
    assert len(r['artifact']['documentClauses'])==2
    assert r['attempts'][0]['status']=='FAILED' and r['artifactDigest']
    p.close()


def test_bad_contract_consent_no_arbitrary_config(tmp_path):
    p=Production(tmp_path)
    src=p.source('test',HTML)
    d=dict(requestId='valid-request',sourceId=src['id'],rules=True,clauses=['第一条'],tests=[],modelConsent=False)
    with pytest.raises(Rejected,match='CONSENT'): p.submit(d)
    with pytest.raises(Rejected): p.submit({**d,'url':'http://attacker'})
    with pytest.raises(Rejected): p.submit({**d,'rules':1})
    with pytest.raises(Rejected): p.submit({**d,'clauses':['不存在']})
    with pytest.raises(Rejected): p.submit({**d,'tests':[{'question':'x'}]})
    assert not p.jobs
    p.close()


def test_only_one_active_run_and_frozen_inputs(tmp_path):
    entered,release=threading.Event(),threading.Event()
    def slow(payload):
        entered.set()
        assert release.wait(5)
        return response(payload)
    p=Production(tmp_path,caller=slow)
    try:
        job,data=submit(p,True)
        assert entered.wait(5)
        with pytest.raises(Rejected,match='PRODUCTION_BUSY'):
            p.submit({**data,'requestId':'second-request'})
        assert p.submit(data)['id']==job['id']
        release.set();done(p,job)
    finally:
        release.set();p.close()


def test_source_jobs_do_not_share_candidates(tmp_path):
    p=Production(tmp_path)
    first,data=submit(p)
    old=done(p,first)
    new=p.source('另一个制度','<html><p>第一条 只包含客服咨询，不含贷款期限。</p></html>')
    second=p.submit({**data,'requestId':'different-source','sourceId':new['id']})
    fresh=done(p,second)
    assert len(fresh['artifact']['documentClauses'])==1
    assert fresh['sourceId']!=old['sourceId']
    assert p.get(first['id'])['artifact']==old['artifact']
    p.close()


def test_candidate_tampering_rejected(tmp_path):
    p=Production(tmp_path)
    job,_=submit(p)
    done(p,job)
    p.jobs[job['id']]['artifact']['status']='PUBLISHED'
    with pytest.raises(Rejected): p.search(job['id'],'第一条')
    p.close()


def test_restart_interrupted_not_retried(tmp_path):
    p=Production(tmp_path)
    job,_=submit(p)
    done(p,job)
    p.close()
    path=tmp_path/(job['id']+'.json')
    data=json.loads(path.read_text());data['status']='RUNNING';persist(path,data)
    p=Production(tmp_path,caller=lambda _:pytest.fail('No auto retry'))
    assert p.get(job['id'])['status']=='INTERRUPTED'
    p.close()


def test_rule_guard_and_missing_engine_are_not_pass(tmp_path,monkeypatch):
    monkeypatch.delenv('KNOWLEDGE_FLOWABLE_CLASSPATH',raising=False)
    p=Production(tmp_path,caller=response)
    job,_=submit(p,True);done(p,job)
    bad=p.rule_test(job['id'],'第一条','duration',{'months':True,'purpose_kind':'CONSUMPTION'})
    assert bad['decision']=='INVALID_INPUT' and bad['engineCalls']==0
    unavailable=p.rule_test(job['id'],'第一条','duration',{'months':48,'purpose_kind':'CONSUMPTION'})
    assert unavailable['decision']=='UNKNOWN' and unavailable['executor']=='NOT_EXECUTED'
    outside=p.rule_test(job['id'],'第一条','duration',{'months':48,'purpose_kind':'BUSINESS'})
    assert outside['decision']=='NOT_APPLICABLE' and outside['engineCalls']==0
    p.close()


def test_http_origin_host_methods_and_script_text(tmp_path):
    p=Production(tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),handler(p))
    t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
    base=f'http://127.0.0.1:{http.server_port}'
    try:
        assert json.load(request.urlopen(base+'/api/state'))['publicationAllowed'] is False
        from web_preview.server import checked, BASELINE_SHA
        from web_production.engine import ROOT
        original = checked(ROOT / 'web_preview/baseline/v1.5.html', BASELINE_SHA).decode()
        css = request.urlopen(base+'/style.css').read().decode()
        assert css.startswith(original.split('<style>', 1)[1].split('</style>', 1)[0])
        assert 'preview.css' not in css
        assert b'/workshop.js' in request.urlopen(base+'/').read()
        assert b'function productionHome()' in request.urlopen(base+'/workshop.js').read()
        for headers in ({},{'Origin':'http://evil.invalid'},{'Origin':base,'Host':'evil.invalid'}):
            req=request.Request(base+'/api/sample',data=b'{}',headers={'Content-Type':'application/json',**headers})
            with pytest.raises(error.HTTPError) as exc: request.urlopen(req)
            assert exc.value.code==403
        payload=json.dumps({'title':'<img src=x onerror=alert(1)>','html':HTML+'<script>attack()</script>'}).encode()
        req=request.Request(base+'/api/sources',data=payload,headers={'Content-Type':'application/json','Origin':base})
        result=json.load(request.urlopen(req))
        assert 'attack()' not in json.dumps(result['clauses'])
        with pytest.raises(error.HTTPError) as exc: request.urlopen(base+'/../.env')
        assert exc.value.code==404
    finally:
        http.shutdown();http.server_close();t.join();p.close()


def test_changed_ui_baseline_refused(tmp_path, monkeypatch):
    import web_production.server as server
    baseline = tmp_path / 'web_preview/baseline/v1.5.html'
    baseline.parent.mkdir(parents=True)
    baseline.write_text('<html><style>changed</style></html>')
    monkeypatch.setattr(server, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='EVIDENCE_DIGEST_MISMATCH'):
        server.handler(None)
