import copy
import hashlib
import json
from pathlib import Path
import time

import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.documents import DocumentCore
from m2.web import DocumentProduction, VerifiedEvaluationHandoff
from m2.synthetic_context import AUTHOR, READER
from tests.test_document_quality_publication import CONFIG
from tests.test_m2_documents import ControlledClient, CASES, RAW
from tests.test_web_production import done


FACTS = {
    '第一条':'每日09:00至17:00',
    '第二条':'在合成客服窗口提交申请',
    '第三条':'应交由人工核实，不得编造缺失信息',
}


class QualityClient(ControlledClient):
    def retrieve_candidates(self, dataset_id, document_id, question, profile):
        self.calls += 1
        if self.error:
            raise Rejected(self.error)
        index=next(i for i,case in enumerate(CASES) if case['question']==question)
        ordered=[self.chunks[index],*[chunk for i,chunk in enumerate(self.chunks) if i!=index]]
        return [{'id':chunk['id'],'text':chunk['text'],'documentId':document_id,
                 'rank':rank,'scoreBps':9000-rank,'termScoreBps':8500,
                 'vectorScoreBps':8000} for rank,chunk in enumerate(ordered,1)]


class TrustedQualityLauncher:
    """Test-only adapter that writes the same immutable Core evidence as a Host."""
    def evaluate(self, database, job, client_factory):
        core,client=DocumentCore(database),client_factory()
        try:
            candidate=job['coreObjects']['candidateDigest']
            _,_,_,index=core._document_parts(AUTHOR,candidate)
            source=index['sourceDigest']
            suffix=candidate[:12]
            profile=core.register_quality_profile(AUTHOR,'workbench-'+suffix,1,CONFIG)
            cases=[]
            for number,legacy in enumerate(job['recipe']['tests'],1):
                clause=legacy['expectedClause']
                cases.append({'caseId':f'workbench-{number}','category':'CANONICAL',
                    'question':legacy['question'],'expectedClauses':[clause],
                    'answerFacts':[FACTS[clause]],'forbiddenClaims':[]})
            test_set={'schemaVersion':'document-quality-test-set.v0.1',
                'id':'workbench-'+suffix,'purpose':'TUNING','sourceDigest':source,
                'sourceTitle':job['title'],'cases':cases}
            tests=core.register_quality_test_set(AUTHOR,candidate,test_set,1)
            retrieval=core.evaluate_quality_retrieval(AUTHOR,candidate,profile,tests,client)
            model={'schemaVersion':'finance-model-selection.v1','defaultModelRef':'model-workbench',
                'connections':[{'modelRef':'model-workbench','configVersion':'sha256:'+'1'*64,
                    'modelName':'deepseek-v4-flash','provider':'OpenAI'}]}
            model_raw=(json.dumps(model,separators=(',',':'))+'\n').encode()
            service={'schemaVersion':'local-agent-service-lock.v0.1',
                'sources':{'factory':{'commit':'1'*40,'worktreeDirty':False}},
                'files':{'model-selection.json':hashlib.sha256(model_raw).hexdigest()}}
            service_raw=(json.dumps(service,separators=(',',':'))+'\n').encode()
            runs=[]
            clauses={value['clause']:value['text'] for value in index['clauses']}
            for number,case in enumerate(cases,1):
                clause=case['expectedClauses'][0]
                chunk=next(value for value in index['index']['chunks'] if clause in value['clauses'])
                evidence={'clause':clause,'quote':clauses[clause],
                    'sourceDigest':source,'originalDigest':index['originalDigest'],
                    'chunkId':chunk['id'],'anchors':[value['anchor'] for value in
                        index['bridge']['mappings'] if value['clause']==clause]}
                receipt={'schemaVersion':'document-receipt.v0.1',
                    'requestId':f'factory-request-{number}','traceId':f'factory-trace-{number}',
                    'principal':'knowledge-agent','productId':'evaluation-'+job['id'],
                    'manifestDigest':'a'*64,'indexDigest':job['coreObjects']['indexDigest'],
                    'sourceDigest':source,'bindingDigest':'b'*64,'policyDigest':'c'*64,
                    'question':case['question'],'hostAuthority':'test-host',
                    'businessContextSource':'test','host':{},
                    'result':{'decision':'EVIDENCE_FOUND','evidence':[evidence]},
                    'createdAt':'2026-11-02T00:00:00Z','mode':'M2_ISOLATED_DOCUMENT'}
                with core.tx():receipt_digest=core._put(AUTHOR,'document-receipt',receipt)
                runtime_raw=json.dumps({'case':number},separators=(',',':')).encode()+b'\n'
                archive={'schemaVersion':'finance-knowledge-answer.v0.1','status':'COMPLETED',
                    'requestId':f'archive-request-{number}','runId':f'archive-run-{number}',
                    'buildId':'factory-workbench','instanceId':'instance-workbench',
                    'serviceLockDigest':hashlib.sha256(service_raw).hexdigest(),
                    'runtimeLockDigest':hashlib.sha256(runtime_raw).hexdigest(),
                    'manifest':'a'*64,'productId':'evaluation-'+job['id'],
                    'response':f'根据{clause}，{FACTS[clause]}。',
                    'toolResults':[{'data':{'result':{'knowledgeReceipt':{
                        'coreReceiptDigest':receipt_digest,'productId':'evaluation-'+job['id'],
                        'manifest':'a'*64,'requestId':receipt['requestId'],
                        'traceId':receipt['traceId']},'evidence':[evidence]}}}]}
                rows=[{'recordType':'model-context','mode':'LIVE','modelRef':'model-workbench',
                        'configVersion':'sha256:'+'1'*64,'modelName':'deepseek-v4-flash'},
                    {'schemaVersion':'finance-observation.v0.1','requestId':archive['requestId'],
                        'instanceId':'instance-workbench','component':'model','operation':'attempt',
                        'phase':'END','outcome':'RETURNED'}]
                runs.append({'caseId':case['caseId'],'archive':archive,
                             'historyRows':rows,'runtimeLockRaw':runtime_raw})
            runtime=core.register_answer_runtime_evidence(AUTHOR,candidate,tests,'a'*64,
                service_raw,model_raw,runs,{'instance':{'instanceId':'instance-workbench',
                'status':'STOPPED'},'stoppedAt':'2026-11-02T00:01:00Z'})
            answer=core.register_answer_evaluation(AUTHOR,candidate,profile,tests,retrieval,runtime)
            admission=core.assess_document_quality(AUTHOR,candidate,profile,tests,retrieval,answer)
            return {'runtimeEvidenceDigest':runtime,'answerEvaluationDigest':answer,
                    'qualityAdmissionDigest':admission}
        finally:core.close()


class ForgedQualityLauncher:
    def evaluate(self, **_):
        return {'runtimeEvidenceDigest':'1'*64,'answerEvaluationDigest':'2'*64,
                'qualityAdmissionDigest':'3'*64}


def make(tmp_path):
    client=QualityClient();client.operations=[]
    service=DocumentProduction(tmp_path,lambda:client,TrustedQualityLauncher())
    source=service.source('合成客服制度',RAW.decode())
    data={'requestId':'m2-ui-request','sourceId':source['id'],'rules':False,'clauses':[],
          'tests':CASES,'modelConsent':False}
    return service,client,data


def release(service,job):
    service.start_evaluation({'runId':job['id'],
        'candidateDigest':job['coreObjects']['candidateDigest']})
    job=evaluated(service,job['id'])
    body={'runId':job['id'],'candidateDigest':job['coreObjects']['candidateDigest'],'reason':'合成材料隔离测试'}
    service.release_action('/api/document-approve',body)
    service.activate_source(body)
    return service.release_action('/api/document-publish',body)


def evaluated(service,run_id):
    for _ in range(100):
        job=service.get(run_id)
        if job.get('qualityEvaluation',{}).get('state') not in {'QUEUED','RUNNING'}:
            return job
        time.sleep(.01)
    raise AssertionError('evaluation did not finish')


def test_server_configured_handoff_rechecks_core_pass(monkeypatch,tmp_path):
    service,client,data=make(tmp_path)
    try:
        result=done(service,service.submit(data))
        trusted=TrustedQualityLauncher().evaluate(
            service.database,result,lambda:client)
        handoff=tmp_path/'trusted-result.json'
        handoff.write_text(json.dumps(trusted),encoding='utf-8')
        assert VerifiedEvaluationHandoff(handoff).evaluate(
            service.database,result,lambda:client)==trusted
        forged={**trusted,'qualityAdmissionDigest':'f'*64}
        handoff.write_text(json.dumps(forged),encoding='utf-8')
        with pytest.raises(Rejected,match='QUALITY_EVALUATION_RESULT_INVALID'):
            VerifiedEvaluationHandoff(handoff).evaluate(
                service.database,result,lambda:client)
    finally:service.close()


def test_web_lifecycle_core_owned_restart_and_no_query_replay(tmp_path):
    service,client,data=make(tmp_path)
    try:
        result=done(service,service.submit(data))
        assert result['status']=='COMPLETED'
        assert result['release']['state']=='EVALUATION_REQUIRED'
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


def test_quality_pass_approval_does_not_activate_source_or_authorize_publish(tmp_path):
    service,_,data=make(tmp_path)
    try:
        job=done(service,service.submit(data))
        service.start_evaluation({'runId':job['id'],
            'candidateDigest':job['coreObjects']['candidateDigest']})
        job=evaluated(service,job['id'])
        body={'runId':job['id'],'candidateDigest':job['coreObjects']['candidateDigest'],
              'reason':'independent release review'}
        approved=service.release_action('/api/document-approve',body)
        assert approved['state']=='APPROVED'
        assert approved['sourceActivationDigest'] is None
        with pytest.raises(Rejected,match='SOURCE_NOT_EFFECTIVE'):
            service.release_action('/api/document-publish',body)
        activated=service.activate_source(body)
        assert activated['sourceActivationDigest']
        with pytest.raises(Rejected,match='SOURCE_ACTIVATION_REPLAY'):
            service.activate_source(body)
        published=service.release_action('/api/document-publish',body)
        assert published['state']=='ISOLATED_PUBLISHED'
    finally:service.close()


def test_workbench_fails_closed_without_trusted_service_or_with_forged_result(tmp_path):
    client=QualityClient();client.operations=[]
    service=DocumentProduction(tmp_path/'disabled',lambda:client)
    source=service.source('合成客服制度',RAW.decode())
    data={'requestId':'disabled-evaluation','sourceId':source['id'],'rules':False,
          'clauses':[],'tests':CASES,'modelConsent':False}
    try:
        job=done(service,service.submit(data))
        assert service.snapshot()['modelReady'] is False
        with pytest.raises(Rejected,match='EVALUATION_SERVICE_NOT_READY'):
            service.start_evaluation({'runId':job['id'],
                'candidateDigest':job['coreObjects']['candidateDigest']})
    finally:service.close()

    service=DocumentProduction(tmp_path/'forged',lambda:client,ForgedQualityLauncher())
    source=service.source('合成客服制度',RAW.decode())
    data={**data,'requestId':'forged-evaluation','sourceId':source['id']}
    try:
        job=done(service,service.submit(data))
        service.start_evaluation({'runId':job['id'],
            'candidateDigest':job['coreObjects']['candidateDigest']})
        result=evaluated(service,job['id'])
        assert result['qualityEvaluation']['state']=='FAILED'
        assert result['release']['state']=='EVALUATION_FAILED'
        with pytest.raises(Rejected,match='QUALITY_ADMISSION_REQUIRED'):
            service.release_action('/api/document-approve',{'runId':job['id'],
                'candidateDigest':job['coreObjects']['candidateDigest'],'reason':'must fail'})
    finally:service.close()


def test_source_version_metadata_is_strict_and_immutable(tmp_path):
    client=QualityClient();client.operations=[]
    service=DocumentProduction(tmp_path,lambda:client)
    metadata={'officialUrl':'https://www.boc.cn/example.html',
        'institution':'中国银行股份有限公司','documentDate':'2025-02-28',
        'version':'2025年2月版',
        'authorityStatus':'PUBLIC_SOURCE_REQUIRES_CURRENT_BUSINESS_REVALIDATION'}
    try:
        source=service.source('中行公开资料',RAW.decode(),metadata)
        assert source['metadata']==metadata
        with pytest.raises(Rejected,match='SOURCE_METADATA_MISMATCH'):
            service.source('相同内容不同登记',RAW.decode(),{**metadata,'version':'另一版本'})
        with pytest.raises(Rejected,match='SOURCE_METADATA_INVALID'):
            service.source('不可信来源',RAW.decode(),{**metadata,'officialUrl':'http://example.test'})
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
        assert second['release']['state']=='EVALUATION_REQUIRED'
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
        service.start_evaluation({'runId':result['id'],'candidateDigest':result['coreObjects']['candidateDigest']})
        result=evaluated(service,result['id'])
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
