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
    def __init__(self):
        self.tamper = False
        self.baseline_calls = 0
        self.quality_profiles = []

    def ingest(self, raw):
        self.chunks = [{'id':f'chunk-{index}', 'text':chunk['text']}
                       for index, chunk in enumerate(parse(raw))]
        return {'datasetId':'quality-dataset', 'documentId':'quality-document',
                'buildId':'quality-build', 'engineIdentity':'CONTROLLED_TEST_ONLY',
                'embeddingIdentity':'NONE', 'chunks':copy.deepcopy(self.chunks)}

    def retrieve(self, dataset, document, question):
        self.baseline_calls += 1
        chunk = self.chunks[0]
        return [{'id':chunk['id'], 'text':chunk['text'], 'documentId':document}]

    def retrieve_candidates(self, dataset, document, question, profile):
        self.quality_profiles.append(copy.deepcopy(profile))
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
        legacy_manifest = core.publish_document(AUTHOR, data['candidateDigest'], validation,
                                                approval, 1)
        legacy_body = core._get(AUTHOR, legacy_manifest, 'document-manifest')
        assert legacy_body['schemaVersion'] == 'document-manifest.v0.1'
        assert 'qualityAdmissionDigest' not in legacy_body
        core.bind_document(AUTHOR, legacy_manifest, 0)
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
            core.publish_document(AUTHOR, data['candidateDigest'], validation, approval, 2)
        with pytest.raises(Rejected, match='QUALITY_MANIFEST_ALREADY_EXISTS'):
            core.publish_quality_document(AUTHOR, data['candidateDigest'], validation,
                                          approval, admission, 1)

        # Later quality admission must not alter an already published v0.1 product.
        baseline_calls = client.baseline_calls
        quality_calls = len(client.quality_profiles)
        legacy_result = core.query_document(READER, 'faq', legacy_manifest, CONTEXT,
            '合成客服服务时间是什么？', 'legacy-request', 'legacy-trace', client)
        assert legacy_result['result']['evidence'][0]['clause'] == '第一条'
        assert client.baseline_calls == baseline_calls + 1
        assert len(client.quality_profiles) == quality_calls

        manifest = core.publish_quality_document(AUTHOR, data['candidateDigest'], validation,
                                                  approval, admission, 2)
        manifest_body = core._get(AUTHOR, manifest, 'document-manifest')
        assert manifest_body['schemaVersion'] == 'document-manifest.v0.1'
        assert 'qualityAdmissionDigest' not in manifest_body
        link_digest = core.db.execute(
            "SELECT digest FROM identities WHERE tenant=? AND kind=? AND name=? AND revision=1",
            (AUTHOR.tenant, 'document-quality-manifest-admission', manifest)).fetchone()[0]
        link = core._get(AUTHOR, link_digest, 'document-quality-manifest-admission')
        assert link['manifestDigest'] == manifest
        assert link['candidateDigest'] == data['candidateDigest']
        assert link['qualityAdmissionDigest'] == admission
        core.bind_document(AUTHOR, manifest, 1)
        result = core.query_document(READER, 'faq', manifest, CONTEXT,
            '合成客服服务时间是什么？', 'quality-request', 'quality-trace', client)
        assert result['result']['evidence'][0]['clause'] == '第一条'
        assert client.quality_profiles[-1] == CONFIG['retrieval']

        # A later PASS for the same Candidate is valid evidence for a future release,
        # but cannot make the existing Manifest ambiguous or change its profile.
        alternate = {**CONFIG,
                     'retrieval':{**CONFIG['retrieval'], 'pageSize':11},
                     'selectionThresholdBps':3200}
        profile_2 = core.register_quality_profile(AUTHOR, 'financial-document-v02-next', 1,
                                                  alternate)
        retrieval_2 = core.evaluate_quality_retrieval(AUTHOR, data['candidateDigest'],
                                                       profile_2, test_digest, client)
        answer_2 = core.register_answer_evaluation(AUTHOR, data['candidateDigest'], profile_2,
            test_digest, retrieval_2, runtime)
        admission_2 = core.assess_document_quality(AUTHOR, data['candidateDigest'], profile_2,
                                                   test_digest, retrieval_2, answer_2)
        assert core._get(AUTHOR, admission_2, 'document-quality-admission')['decision'] == 'PASS'
        repeated = core.query_document(READER, 'faq', manifest, CONTEXT,
            '合成客服服务时间是什么？', 'quality-request-2', 'quality-trace-2', client)
        assert repeated['result']['evidence'][0]['clause'] == '第一条'
        assert client.quality_profiles[-1] == CONFIG['retrieval']

        client.tamper = True
        with pytest.raises(Rejected, match='QUALITY_RETRIEVAL_INDEX_MISMATCH'):
            core.evaluate_quality_retrieval(AUTHOR, data['candidateDigest'], profile,
                                            test_digest, client)
    finally:
        core.close()
