from dataclasses import replace
import asyncio
from types import SimpleNamespace

import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.core import Actor
from knowledge_core.documents import DocumentCore
from evaluation_worker import CandidateEvaluationWorker, OpenJiuwenModelGateway
from evaluation_worker.gateway import _bounded_usage
from m2.pipeline import produce
from tests.support import CONTEXT, ir, policy
from tests.test_document_quality_publication import (
    AUTHOR as QUALITY_AUTHOR, CONFIG, LEGACY, RAW, QualityClient, quality_set,
)


MANAGER = replace(QUALITY_AUTHOR, privileges=QUALITY_AUTHOR.privileges | {
    'source.classify', 'evaluation.manage', 'evaluation.lease.issue',
    'model.gateway.manage', 'model.egress.authorize',
})
WORKER = Actor(MANAGER.tenant, 'factory-evaluation-worker', 'worker-build-001',
               frozenset({'evaluation.execute'}))
GATEWAY = Actor(MANAGER.tenant, 'factory-model-gateway', 'gateway-receipts-v1',
                frozenset({'model.receipt.record'}))
FUTURE = '2099-01-01T00:00:00+00:00'


def test_model_usage_excludes_floats_and_unbounded_provider_metadata():
    usage = SimpleNamespace(model_dump=lambda: {
        'input_tokens':12, 'output_tokens':3, 'total_tokens':15,
        'total_latency':1.25, 'prompt':'sensitive prompt', 'unknown':999})
    assert _bounded_usage(usage) == {
        'inputTokens':12, 'outputTokens':3, 'totalTokens':15}


def evaluation_policy():
    value = policy()
    value['grants'].append({
        'principal':WORKER.principal,
        'resource':'source:faq-source',
        'actions':['source_read'],
    })
    return value


def prepare(tmp_path, classification='PUBLIC', external_allowed=True):
    core, client = DocumentCore(tmp_path / 'core.db'), QualityClient()
    core.set_policy(MANAGER, evaluation_policy(), 0)
    data = produce(core, MANAGER, 'faq', 1, RAW, ir()['rules'][0]['scope'],
                   LEGACY, ['reader'], client)
    core.activate_source(MANAGER, data['sourceDigest'], '2026-01-01')
    validation = core.validate_document(MANAGER, data['candidateDigest'], client)
    approval = core.approve_document(MANAGER, data['candidateDigest'], validation, 'quality')
    profile = core.register_quality_profile(MANAGER, 'worker-quality', 1, CONFIG)
    tests = core.register_quality_test_set(
        MANAGER, data['candidateDigest'], quality_set(data['sourceDigest']), 1)
    retrieval = core.evaluate_quality_retrieval(
        MANAGER, data['candidateDigest'], profile, tests, client)
    classification_digest = core.register_source_classification(
        MANAGER, 'faq-source-classification', 1, data['sourceDigest'],
        classification, external_allowed,
        ['volcengine'] if external_allowed else [],
        ['cn-beijing'] if external_allowed else [], ['factory-dev'])
    prompt = core.register_evaluation_prompt_template(
        MANAGER, 'grounded-answer', 1,
        '仅根据提供的原文回答；证据不足时明确拒答。',
        '给出直接结论并明确引用条款编号。')
    assignment = core.create_evaluation_assignment(
        MANAGER, 'faq-evaluation', 1, data['candidateDigest'], tests, profile,
        retrieval, classification_digest, 'b' * 64, prompt, CONTEXT, FUTURE)
    lease = core.issue_evaluation_lease(
        MANAGER, 'faq-worker-lease', 1, assignment, WORKER.principal,
        WORKER.authority, FUTURE, 'lease-nonce-1')
    gateway = core.register_model_gateway(
        MANAGER, 'factory-model-gateway', 1, GATEWAY.principal, 'd' * 64,
        'volcengine-openai-v1', ['volcengine'], ['deepseek-v4-flash'],
        ['cn-beijing'], GATEWAY.authority, 'e' * 64)
    return core, client, {
        **data, 'validation':validation, 'approval':approval, 'profile':profile,
        'tests':tests, 'retrieval':retrieval, 'classification':classification_digest,
        'assignment':assignment, 'lease':lease, 'gateway':gateway, 'prompt':prompt,
    }


def run_candidate(core, client, values):
    receipt = core.query_document_candidate_for_evaluation(
        WORKER, values['assignment'], values['lease'], 'quality-service-hours',
        'candidate-request-1', 'candidate-trace-1', client)
    authorization = core.authorize_model_egress(
        MANAGER, 'faq-egress', 1, values['assignment'], receipt['receiptDigest'],
        'volcengine', 'deepseek-v4-flash', 'b' * 64, 'cn-beijing',
        'answer-quality', 'factory-dev', True, 'source-only', FUTURE)
    request = core.prepare_model_invocation(GATEWAY, values['gateway'], authorization)
    model_receipt = core.record_model_invocation(
        GATEWAY, values['gateway'], authorization, 'model-request-1',
        'model-trace-1', '2026-11-01T00:00:00+00:00',
        '2026-11-01T00:00:01+00:00', 'RETURNED',
        '根据第一条，合成客服服务时间为每日09:00至17:00。',
        'provider-request-1', {'inputTokens':100, 'outputTokens':20},
        request['requestPayloadDigest'])
    return receipt, authorization, model_receipt


def test_factory_worker_candidate_to_quality_admission(tmp_path):
    core, client, values = prepare(tmp_path)
    try:
        candidate_receipt, _, model_receipt = run_candidate(core, client, values)
        runtime = core.register_factory_evaluation_runtime_evidence(
            MANAGER, values['assignment'], values['lease'], 'a' * 64,
            '3.12', '0.1.17.post1', [{
                'caseId':'quality-service-hours',
                'candidateReceiptDigest':candidate_receipt['receiptDigest'],
                'modelReceiptDigest':model_receipt,
            }])
        runtime_body = core._get(
            MANAGER, runtime, 'document-factory-evaluation-runtime-evidence')
        assert runtime_body['verification'] == 'CORE_CORRELATED_FACTORY_WORKER'
        assert 'buildId' not in runtime_body
        assert 'instanceId' not in runtime_body
        assert 'installationLockDigest' not in runtime_body

        answer = core.register_answer_evaluation(
            MANAGER, values['candidateDigest'], values['profile'], values['tests'],
            values['retrieval'], runtime)
        answer_body = core._get(MANAGER, answer, 'document-answer-evaluation')
        assert answer_body['schemaVersion'] == 'document-answer-evaluation.v0.3'
        assert answer_body['evidenceAuthority'] == 'FACTORY_WORKER'
        admission = core.assess_document_quality(
            MANAGER, values['candidateDigest'], values['profile'], values['tests'],
            values['retrieval'], answer)
        admission_body = core._get(MANAGER, admission, 'document-quality-admission')
        assert admission_body['schemaVersion'] == 'document-quality-admission.v0.2'
        assert admission_body['answerEvidenceAuthority'] == 'FACTORY_WORKER'
        assert admission_body['decision'] == 'PASS'

        manifest = core.publish_quality_document(
            MANAGER, values['candidateDigest'], values['validation'],
            values['approval'], admission, 1)
        assert core._get(MANAGER, manifest, 'document-manifest')[
            'schemaVersion'] == 'document-manifest.v0.1'
    finally:
        core.close()


def test_worker_cannot_forge_model_receipt_or_replay_candidate_query(tmp_path):
    core, client, values = prepare(tmp_path)
    try:
        candidate_receipt = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'], 'quality-service-hours',
            'candidate-request-1', 'candidate-trace-1', client)
        authorization = core.authorize_model_egress(
            MANAGER, 'faq-egress', 1, values['assignment'],
            candidate_receipt['receiptDigest'], 'volcengine', 'deepseek-v4-flash',
            'b' * 64, 'cn-beijing', 'answer-quality', 'factory-dev', True,
            'source-only', FUTURE)
        with pytest.raises(Rejected, match='FORBIDDEN'):
            core.record_model_invocation(
                WORKER, values['gateway'], authorization, 'forged-request',
                'forged-trace', '2026-11-01T00:00:00+00:00',
                '2026-11-01T00:00:01+00:00', 'RETURNED', 'forged',
                'forged-provider-request', {}, 'f' * 64)
        with pytest.raises(Rejected, match='EVALUATION_LEASE_REPLAYED'):
            core.query_document_candidate_for_evaluation(
                WORKER, values['assignment'], values['lease'],
                'quality-service-hours', 'candidate-request-2',
                'candidate-trace-2', client)
    finally:
        core.close()


def test_source_revocation_and_restricted_egress_fail_closed(tmp_path):
    core, client, values = prepare(
        tmp_path, classification='RESTRICTED', external_allowed=False)
    try:
        receipt = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'], 'quality-service-hours',
            'candidate-request-1', 'candidate-trace-1', client)
        with pytest.raises(Rejected, match='EVALUATION_EGRESS_FORBIDDEN'):
            core.authorize_model_egress(
                MANAGER, 'restricted-egress', 1, values['assignment'],
                receipt['receiptDigest'], 'volcengine', 'deepseek-v4-flash',
                'b' * 64, 'cn-beijing', 'answer-quality', 'factory-dev', True,
                'source-only', FUTURE)
    finally:
        core.close()

    other = tmp_path / 'revoked'
    other.mkdir()
    core, client, values = prepare(other)
    try:
        core.activate_source(MANAGER, values['sourceDigest'], '2026-11-01', 'REVOKED')
        with pytest.raises(Rejected, match='SOURCE_SUPERSEDED_OR_REVOKED'):
            core.query_document_candidate_for_evaluation(
                WORKER, values['assignment'], values['lease'],
                'quality-service-hours', 'candidate-request-1',
                'candidate-trace-1', client)
    finally:
        core.close()


def test_failed_model_attempt_cannot_be_admitted(tmp_path):
    core, client, values = prepare(tmp_path)
    try:
        candidate_receipt = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'], 'quality-service-hours',
            'candidate-request-1', 'candidate-trace-1', client)
        authorization = core.authorize_model_egress(
            MANAGER, 'faq-egress', 1, values['assignment'],
            candidate_receipt['receiptDigest'], 'volcengine', 'deepseek-v4-flash',
            'b' * 64, 'cn-beijing', 'answer-quality', 'factory-dev', True,
            'source-only', FUTURE)
        failed = core.record_model_invocation(
            GATEWAY, values['gateway'], authorization, 'model-request-failed',
            'model-trace-failed', '2026-11-01T00:00:00+00:00',
            '2026-11-01T00:00:01+00:00', 'FAILED', None,
            'provider-request-failed', {'errorClass':'UPSTREAM_UNAVAILABLE'},
            core.prepare_model_invocation(
                GATEWAY, values['gateway'], authorization)['requestPayloadDigest'])
        with pytest.raises(Rejected, match='QUALITY_RUNTIME_RECEIPT_MISMATCH'):
            core.register_factory_evaluation_runtime_evidence(
                MANAGER, values['assignment'], values['lease'], 'a' * 64,
                '3.12', '0.1.17.post1', [{
                    'caseId':'quality-service-hours',
                    'candidateReceiptDigest':candidate_receipt['receiptDigest'],
                    'modelReceiptDigest':failed,
                }])
    finally:
        core.close()


def test_fixed_worker_uses_only_core_prepared_outbound_payload(tmp_path):
    core, client, values = prepare(tmp_path)
    outbound = []

    class Model:
        async def invoke(self, messages, **kwargs):
            return SimpleNamespace(
                content='根据第一条，合成客服服务时间为每日09:00至17:00。',
                usage_metadata=None, metadata={'request_id':'provider-real-1'})

    def authorize(candidate):
        return core.authorize_model_egress(
            MANAGER, 'worker-egress', 1, values['assignment'],
            candidate['receiptDigest'], 'volcengine', 'deepseek-v4-flash',
            'b' * 64, 'cn-beijing', 'answer-quality', 'factory-dev', True,
            'source-only', FUTURE)

    try:
        gateway = OpenJiuwenModelGateway(
            core, GATEWAY, values['gateway'], Model(), outbound.append)
        worker = CandidateEvaluationWorker(
            core, WORKER, gateway, client, authorize)
        runs = asyncio.run(worker.run(
            values['assignment'], values['lease'], ['quality-service-hours']))
        assert len(runs) == 1
        assert len(outbound) == 1
        assert set(outbound[0]) == {'messages', 'model', 'temperature'}
        serialized = repr(outbound[0])
        assert 'tenant-a' not in serialized
        assert WORKER.principal not in serialized
        assert 'faq-source' not in serialized
        receipt = core._get(
            MANAGER, runs[0]['modelReceiptDigest'], 'model-invocation-receipt')
        assert receipt['providerRequestRef'] == 'provider-real-1'
    finally:
        core.close()


def test_gateway_does_not_mislabel_gateway_id_as_provider_id(tmp_path):
    core, client, values = prepare(tmp_path)

    class Model:
        async def invoke(self, messages, **kwargs):
            return SimpleNamespace(
                content='根据第一条，合成客服服务时间为每日09:00至17:00。',
                usage_metadata=None, metadata={})

    try:
        candidate = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'],
            'quality-service-hours', 'candidate-request-1',
            'candidate-trace-1', client)
        authorization = core.authorize_model_egress(
            MANAGER, 'worker-egress', 1, values['assignment'],
            candidate['receiptDigest'], 'volcengine', 'deepseek-v4-flash',
            'b' * 64, 'cn-beijing', 'answer-quality', 'factory-dev', True,
            'source-only', FUTURE)
        gateway = OpenJiuwenModelGateway(
            core, GATEWAY, values['gateway'], Model())
        receipt_digest = asyncio.run(gateway.invoke(
            authorization, 'gateway-request-1', 'gateway-trace-1'))
        receipt = core._get(
            MANAGER, receipt_digest, 'model-invocation-receipt')
        assert receipt['providerRequestRef'] == \
            'unavailable:gateway-request-1'
    finally:
        core.close()


def test_gateway_rejects_payload_tamper_and_post_query_source_revocation(tmp_path):
    core, client, values = prepare(tmp_path)
    try:
        candidate = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'], 'quality-service-hours',
            'candidate-request-1', 'candidate-trace-1', client)
        authorization = core.authorize_model_egress(
            MANAGER, 'faq-egress', 1, values['assignment'],
            candidate['receiptDigest'], 'volcengine', 'deepseek-v4-flash',
            'b' * 64, 'cn-beijing', 'answer-quality', 'factory-dev', True,
            'source-only', FUTURE)
        with pytest.raises(Rejected, match='EVALUATION_MODEL_REQUEST_MISMATCH'):
            core.record_model_invocation(
                GATEWAY, values['gateway'], authorization, 'tampered-request',
                'tampered-trace', '2026-11-01T00:00:00+00:00',
                '2026-11-01T00:00:01+00:00', 'RETURNED', 'tampered',
                'provider-tampered', {}, 'f' * 64)
        core.activate_source(MANAGER, values['sourceDigest'], '2026-11-01', 'REVOKED')
        with pytest.raises(Rejected, match='SOURCE_SUPERSEDED_OR_REVOKED'):
            core.prepare_model_invocation(
                GATEWAY, values['gateway'], authorization)
    finally:
        core.close()
