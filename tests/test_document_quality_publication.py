import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.documents import DocumentCore
from m2.pipeline import parse, produce
from m2.ragflow import BASELINE_RETRIEVAL
from tests.support import AUTHOR as BASE_AUTHOR, CONTEXT, READER, ir, policy


AUTHOR = replace(BASE_AUTHOR, privileges=BASE_AUTHOR.privileges | {'document.approve'})
RAW = (Path(__file__).parent / 'fixtures/m2-document.html').read_bytes()
LEGACY = [{'question':'合成客服服务时间是什么？', 'expectedClause':'第一条'}]
CONFIG = {'retrieval':{**BASELINE_RETRIEVAL, 'pageSize':12, 'keywordWeightBps':5000},
          'postRank':'STRUCTURE_V0_2', 'selectionThresholdBps':3300,
          'queryPlanner':'DETERMINISTIC_FINANCIAL_V0_1',
          'supportPolicy':'EVIDENCE_SUPPORT_V0_1'}


class QualityClient:
    tamper = False
    def ingest(self, raw):
        self.chunks = [{'id':f'chunk-{index}', 'text':chunk['text']}
                       for index, chunk in enumerate(parse(raw))]
        return {'datasetId':'quality-dataset', 'documentId':'quality-document',
                'buildId':'quality-build', 'engineIdentity':'CONTROLLED_TEST_ONLY',
                'embeddingIdentity':'NONE', 'chunks':copy.deepcopy(self.chunks)}

    def retrieve(self, dataset, document, question):
        chunk = self.chunks[0]
        return [{'id':chunk['id'], 'text':chunk['text'], 'documentId':document}]

    def retrieve_candidates(self, dataset, document, question, profile):
        return [{'id':chunk['id'], 'text':chunk['text'] + ('tampered' if self.tamper else ''), 'documentId':document,
                 'rank':rank, 'scoreBps':9000 - rank, 'termScoreBps':8000,
                 'vectorScoreBps':8000} for rank, chunk in enumerate(self.chunks, 1)]


def quality_set(source_digest):
    cases = [{'caseId':'quality-service-hours', 'category':'CANONICAL',
              'question':'合成客服服务时间是什么？', 'expectedClauses':['第一条'],
              'answerFacts':['每日09:00至17:00'], 'forbiddenClaims':[]}]
    return {'schemaVersion':'document-quality-test-set.v0.1', 'id':'quality-frozen-test',
            'purpose':'TUNING', 'sourceDigest':source_digest,
            'sourceTitle':'合成客服制度', 'cases':cases}


def runtime_evidence(core, candidate, test_digest, source_digest, tamper=False):
    model = {'schemaVersion':'finance-model-selection.v1', 'defaultModelRef':'model-ea-002',
             'connections':[{'modelRef':'model-ea-002', 'configVersion':'sha256:' + '1' * 64,
                             'modelName':'deepseek-v4-flash', 'provider':'OpenAI'}]}
    model_raw = (json.dumps(model, separators=(',', ':')) + '\n').encode()
    service = {'schemaVersion':'local-agent-service-lock.v0.1',
               'sources':{'builder':{'commit':'1' * 40, 'worktreeDirty':False},
                          'harness':{'commit':'2' * 40, 'worktreeDirty':False}},
               'files':{'model-selection.json':hashlib.sha256(model_raw).hexdigest()}}
    service_raw = (json.dumps(service, separators=(',', ':')) + '\n').encode()
    runtime_raw = b'{"runtime":"verified"}\n'
    evidence = {'clause':'第一条', 'quote':'第一条 服务时间为每日09:00至17:00。',
                'sourceDigest':source_digest, 'originalDigest':'e' * 64, 'chunkId':'chunk-1'}
    receipt = {'schemaVersion':'document-receipt.v0.1', 'requestId':'factory-request',
        'traceId':'factory-trace', 'principal':'reader', 'productId':'faq',
        'manifestDigest':'a' * 64, 'indexDigest':'b' * 64, 'sourceDigest':source_digest,
        'bindingDigest':'c' * 64, 'policyDigest':'d' * 64,
        'question':'合成客服服务时间是什么？', 'hostAuthority':'test-host',
        'businessContextSource':'test', 'host':{},
        'result':{'decision':'EVIDENCE_FOUND', 'evidence':[evidence]},
        'createdAt':'2026-11-01T00:00:00Z', 'mode':'M2_ISOLATED_DOCUMENT'}
    with core.tx():
        receipt_digest = core._put(AUTHOR, 'document-receipt', receipt)
    archive = {'schemaVersion':'finance-knowledge-answer.v0.1', 'status':'COMPLETED',
        'requestId':'archive-request', 'runId':'archive-run', 'buildId':'agent-quality',
        'instanceId':'instance-quality', 'serviceLockDigest':hashlib.sha256(service_raw).hexdigest(),
        'runtimeLockDigest':hashlib.sha256(runtime_raw).hexdigest(), 'manifest':'a' * 64,
        'productId':'faq', 'response':'根据第一条，服务时间为每日09:00至17:00。',
        'toolResults':[{'data':{'result':{'knowledgeReceipt':{
            'coreReceiptDigest':receipt_digest, 'productId':'faq', 'manifest':'a' * 64,
            'requestId':'factory-request', 'traceId':'factory-trace'},
            'evidence':[{**evidence, 'quote':'伪造引用'}] if tamper else [evidence]}}}]}
    rows = [
        {'recordType':'model-context', 'mode':'LIVE', 'modelRef':'model-ea-002',
         'configVersion':'sha256:' + '1' * 64, 'modelName':'deepseek-v4-flash'},
        {'schemaVersion':'finance-observation.v0.1', 'requestId':'archive-request',
         'instanceId':'instance-quality', 'component':'model', 'operation':'attempt',
         'phase':'END', 'outcome':'RETURNED'},
    ]
    return core.register_answer_runtime_evidence(AUTHOR, candidate, test_digest,
        'a' * 64, service_raw, model_raw,
        [{'caseId':'quality-service-hours', 'archive':archive,
          'historyRows':rows, 'runtimeLockRaw':runtime_raw}],
        {'instance':{'instanceId':'instance-quality', 'status':'STOPPED'},
         'stoppedAt':'2026-11-01T00:01:00Z'})


def test_quality_enrollment_cannot_bypass_core_recomputed_gate(tmp_path):
    core, client = DocumentCore(tmp_path / 'core.db'), QualityClient()
    try:
        core.set_policy(AUTHOR, policy(), 0)
        data = produce(core, AUTHOR, 'faq', 1, RAW, ir()['rules'][0]['scope'],
                       LEGACY, ['reader'], client)
        core.activate_source(AUTHOR, data['sourceDigest'], '2026-01-01')
        validation = core.validate_document(AUTHOR, data['candidateDigest'], client)
        approval = core.approve_document(AUTHOR, data['candidateDigest'], validation, 'test')
        profile = core.register_quality_profile(AUTHOR, 'financial-document-v02', 1, CONFIG)
        test_set = quality_set(data['sourceDigest'])
        test_digest = core.register_quality_test_set(AUTHOR, data['candidateDigest'], test_set, 1)
        retrieval = core.evaluate_quality_retrieval(AUTHOR, data['candidateDigest'], profile,
                                                     test_digest, client)
        runtime = runtime_evidence(core, data['candidateDigest'], test_digest,
                                   data['sourceDigest'])
        runtime_case = core._get(AUTHOR, runtime, 'document-answer-runtime-evidence')['cases'][0]
        assert runtime_case['retrievedEvidence'][0]['clause'] == '第一条'
        assert runtime_case['answerCitations'][0]['clause'] == '第一条'
        assert runtime_case['unmatchedAnswerCitations'] == []
        with pytest.raises(Rejected, match='QUALITY_RUNTIME_EVIDENCE_MISMATCH'):
            runtime_evidence(core, data['candidateDigest'], test_digest,
                             data['sourceDigest'], tamper=True)
        answer = core.register_answer_evaluation(AUTHOR, data['candidateDigest'], profile,
            test_digest, retrieval, runtime)
        admission = core.assess_document_quality(AUTHOR, data['candidateDigest'], profile,
                                                 test_digest, retrieval, answer)
        assert core._get(AUTHOR, admission, 'document-quality-admission')['decision'] == 'PASS'
        with pytest.raises(Rejected, match='QUALITY_ADMISSION_REQUIRED'):
            core.publish_document(AUTHOR, data['candidateDigest'], validation, approval, 1)
        manifest = core.publish_quality_document(AUTHOR, data['candidateDigest'], validation,
                                                  approval, admission, 1)
        assert core._get(AUTHOR, manifest, 'document-manifest')['schemaVersion'] == 'document-manifest.v0.1'
        core.bind_document(AUTHOR, manifest, 0)
        result = core.query_document(READER, 'faq', manifest, CONTEXT,
            '合成客服服务时间是什么？', 'quality-request', 'quality-trace', client)
        assert result['result']['evidence'][0]['clause'] == '第一条'

        client.tamper = True
        with pytest.raises(Rejected, match='QUALITY_RETRIEVAL_INDEX_MISMATCH'):
            core.evaluate_quality_retrieval(AUTHOR, data['candidateDigest'], profile,
                                            test_digest, client)
    finally:
        core.close()
