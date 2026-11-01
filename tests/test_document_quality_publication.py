import copy
from dataclasses import replace
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
        answers = []
        for case in test_set['cases']:
            answers.append({'caseId':case['caseId'],
                'answer':'服务时间为每日09:00至17:00。', 'citedClauses':['第一条']})
        retrieval = core.evaluate_quality_retrieval(AUTHOR, data['candidateDigest'], profile,
                                                     test_digest, client)
        answer = core.register_answer_evaluation(AUTHOR, data['candidateDigest'], profile,
            test_digest, retrieval, 'REAL_HARNESS_DEEPSEEK', 'controlled-test-model', answers)
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
