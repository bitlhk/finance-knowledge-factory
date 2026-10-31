import json
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected
from m2.web import DocumentProduction
from m2.synthetic_context import AUTHOR, READER
from tests.test_m2_documents import ControlledClient, CASES, RAW
from tests.test_web_production import done


def make(tmp_path):
    client=ControlledClient();client.operations=[]
    service=DocumentProduction(tmp_path,lambda:client)
    source=service.source('合成客服制度',RAW.decode())
    data={'requestId':'m2-ui-request','sourceId':source['id'],'rules':False,'clauses':[],
          'tests':CASES,'modelConsent':False}
    return service,client,data


def release(service,job):
    body={'runId':job['id'],'candidateDigest':job['coreObjects']['candidateDigest'],'reason':'合成材料隔离测试'}
    service.release_action('/api/document-approve',body)
    return service.release_action('/api/document-publish',body)


def test_web_lifecycle_core_owned_restart_and_no_query_replay(tmp_path):
    service,client,data=make(tmp_path)
    try:
        result=done(service,service.submit(data))
        assert result['status']=='COMPLETED'
        assert result['release']['state']=='VALIDATED'
        assert result['recipe']['documentPipeline'].startswith('native-ragflow')
        with pytest.raises(Rejected,match='DOCUMENT_NOT_PUBLISHED'):service.search(result['id'],CASES[0]['question'])
        bound=release(service,result)
        assert bound['state']=='ISOLATED_PUBLISHED'
        answer=service.search(result['id'],CASES[0]['question'])
        assert answer['receipt']['manifestDigest']==bound['manifestDigest']
        assert service.submit(data)['id']==result['id']
        saved=json.loads((tmp_path/(result['id']+'.json')).read_text())
        assert 'release' not in saved and 'manifestDigest' not in saved
        before=client.calls
        service.close()
        service=DocumentProduction(tmp_path,lambda:pytest.fail('Reading history must not connect to upstream'))
        restored=service.get(result['id'])
        assert restored['release']==bound
        assert restored['consumptionReceipts'][0]['receipt']['result']==answer['receipt']['result']
        assert client.calls==before
        assert len(service.snapshot()['isolatedReleases'])==1
    finally:service.close()


def test_web_cannot_publish_or_spoof_identity(tmp_path):
    service,client,data=make(tmp_path)
    try:
        result=done(service,service.submit(data))
        body={'runId':result['id'],'candidateDigest':result['coreObjects']['candidateDigest'],'reason':'test'}
        with pytest.raises(Rejected,match='DOCUMENT_APPROVAL_REQUIRED'):
            service.release_action('/api/document-publish',body)
        with pytest.raises(Rejected,match='RELEASE_CONTRACT_INVALID'):
            service.release_action('/api/document-approve',{**body,'actor':'admin'})
        with pytest.raises(Rejected,match='CANDIDATE_MISMATCH'):
            service.release_action('/api/document-approve',{**body,'candidateDigest':'0'*64})
        with pytest.raises(Rejected,match='DOCUMENT_ONLY_REQUIRED'):service.submit({**data,'rules':True})
        with pytest.raises(Rejected,match='RETRIEVAL_GOLD_REQUIRED'):service.submit({**data,'tests':[]})
    finally:service.close()


def test_failed_retrieval_preserves_candidate_no_approval(tmp_path):
    service,client,data=make(tmp_path);client.error='RAGFLOW_BUSINESS_ERROR'
    try:
        result=done(service,service.submit(data))
        assert result['status']=='PARTIAL' and result['artifactDigest']
        with pytest.raises(Rejected,match='CANDIDATE_NOT_VALIDATED'):release(service,result)
        assert not service.snapshot()['isolatedReleases']
    finally:service.close()


def test_two_productions_do_not_change_first_binding(tmp_path):
    service,_,data=make(tmp_path)
    try:
        first=done(service,service.submit(data));binding=release(service,first)
        second=done(service,service.submit({**data,'requestId':'another-request'}))
        assert second['id']!=first['id']
        assert second['release']['state']=='VALIDATED'
        assert service.get(first['id'])['release']==binding
    finally:service.close()


def test_release_http_same_origin_and_no_privilege_parameters(tmp_path):
    from http.server import ThreadingHTTPServer
    from urllib import request, error
    import threading
    from web_production.server import handler
    service,_,data=make(tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),handler(service))
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def post(body,origin):
        req=request.Request(base+'/api/document-approve',json.dumps(body).encode(),
            headers={'Content-Type':'application/json','Origin':origin})
        try:
            with request.urlopen(req) as response:return response.status,json.load(response)
        except error.HTTPError as exc:return exc.code,json.load(exc)
    try:
        result=done(service,service.submit(data))
        body={'runId':result['id'],'candidateDigest':result['coreObjects']['candidateDigest'],'reason':'isolated test'}
        assert post(body,'https://untrusted.invalid')[0]==403
        assert post({**body,'principal':'admin'},base)==(409,{'error':'RELEASE_CONTRACT_INVALID'})
        assert post(body,base)[1]['state']=='APPROVED'
        with request.urlopen(base+'/workshop.js') as response:assert not response.read().endswith(b'init();\n')
        with request.urlopen(base+'/m2.js') as response:assert response.read().endswith(b'init();\n')
    finally:http.shutdown();http.server_close();thread.join();service.close()


def test_published_status_uses_manifest_frozen_validation_and_approval(tmp_path):
    service,client,data=make(tmp_path)
    try:
        job=done(service,service.submit(data));frozen=release(service,job)
        client.error='RAGFLOW_BUSINESS_ERROR'
        core=service.core()
        try:core.validate_document(AUTHOR,job['coreObjects']['candidateDigest'],client)
        finally:core.close()
        assert service.get(job['id'])['release']==frozen
        result=service.release_action('/api/document-approve',{'runId':job['id'],
            'candidateDigest':job['coreObjects']['candidateDigest'],'reason':'repeat should not change approval'})
        assert result==frozen
    finally:service.close()


def test_revocation_and_upstream_error_do_not_disclose_or_replay_as_success(tmp_path):
    service,client,data=make(tmp_path)
    try:
        job=done(service,service.submit(data));release(service,job)
        receipt=service.search(job['id'],CASES[0]['question'])
        client.error='RAGFLOW_BUSINESS_ERROR'
        with pytest.raises(Rejected):service.search(job['id'],CASES[0]['question'])
        assert len(service.get(job['id'])['consumptionReceipts'])==1
        assert service.get(job['id'])['consumptionReceipts'][0]['id']==receipt['id']
        core=service.core()
        try:
            revision,sha=core._head(AUTHOR,'policy','current')
            policy=core._get(AUTHOR,sha,'active-policy')
            policy['revision']=revision+1
            policy['grants']=[g for g in policy['grants'] if not(g['principal']==READER.principal and g['resource'].startswith('source:'))]
            core.set_policy(AUTHOR,policy,revision)
        finally:core.close()
        before=client.calls
        with pytest.raises(Rejected):service.search(job['id'],CASES[0]['question'])
        assert client.calls==before
    finally:service.close()
