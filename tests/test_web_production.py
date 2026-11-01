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



def test_http_origin_host_methods_and_script_text(tmp_path):
    p=Production(tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),handler(p))
    t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
    base=f'http://127.0.0.1:{http.server_port}'
    try:
        assert json.load(request.urlopen(base+'/api/state'))['publicationAllowed'] is False
        from web_production.assets import checked, BASELINE_SHA
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
