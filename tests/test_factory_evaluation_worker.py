from dataclasses import replace
import asyncio
import json
from types import SimpleNamespace

import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.core import Actor
from knowledge_core.documents import DocumentCore
from evaluation_worker import (CandidateEvaluationWorker, CandidateQueryClient,
                               CoreModelGatewayClient, ModelAuthorizationClient,
                               ModelDeployment, ModelEnvironment,
                               OpenJiuwenModelGateway, model_config_digest)
from evaluation_worker.gateway import _bounded_usage
from knowledge_core.documents import _answer_references
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
ENVIRONMENT = ModelEnvironment(
    'https://model.example.test/v1', 'deepseek-v4-flash', 'test-key')
DEPLOYMENT = ModelDeployment(
    'volcengine-deepseek', 'volcengine', ENVIRONMENT.api_base,
    'cn-beijing', 'factory-dev', True, 'd' * 64,
    'openjiuwen-model-v0.1', 'e' * 64)
MODEL_CONFIG = model_config_digest(DEPLOYMENT.provider, ENVIRONMENT)


class APIStatusError(Exception):
    pass


def test_model_usage_excludes_floats_and_unbounded_provider_metadata():
    usage = SimpleNamespace(model_dump=lambda: {
        'input_tokens':12, 'output_tokens':3, 'total_tokens':15,
        'total_latency':1.25, 'prompt':'sensitive prompt', 'unknown':999})
    assert _bounded_usage(usage) == {
        'inputTokens':12, 'outputTokens':3, 'totalTokens':15}


def test_answer_citations_resolve_core_numbered_evidence_and_reject_unknown():
    retrieved = [
        {'clause':'第一条', 'evidenceDigest':'a' * 64},
        {'clause':'第二条', 'evidenceDigest':'b' * 64},
    ]
    citations, unmatched = _answer_references(
        '根据已核验原文[1]可以确认；[9]无对应原文。', retrieved)
    assert citations == [{
        'clause':'第一条', 'answerReference':'[1]',
        'retrievedEvidenceDigests':['a' * 64],
        'derivation':'ARCHIVED_ANSWER_EVIDENCE_ORDINAL',
    }]
    assert unmatched == ['[9]']


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
        retrieval, classification_digest, MODEL_CONFIG, prompt, CONTEXT, FUTURE)
    lease = core.issue_evaluation_lease(
        MANAGER, 'faq-worker-lease', 1, assignment, WORKER.principal,
        WORKER.authority, 'a' * 64, FUTURE, 'lease-nonce-1')
    gateway = core.register_model_gateway(
        MANAGER, 'factory-model-gateway', 1, GATEWAY.principal,
        DEPLOYMENT.gateway_build_digest, DEPLOYMENT.adapter_version,
        [DEPLOYMENT.registration(ENVIRONMENT)], GATEWAY.authority,
        DEPLOYMENT.qualification_digest)
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
        values['gateway'], DEPLOYMENT.id, CONTEXT.purpose, 'source-only', FUTURE)
    request = core.prepare_model_invocation(
        GATEWAY, values['gateway'], authorization, 'model-request-1',
        'model-trace-1', DEPLOYMENT.runtime_identity(ENVIRONMENT))
    model_receipt = core.record_model_invocation(
        GATEWAY, values['gateway'], authorization,
        request['invocationAttemptDigest'], '2026-11-01T00:00:00+00:00',
        '2026-11-01T00:00:01+00:00', 'RETURNED',
        '根据第一条，合成客服服务时间为每日09:00至17:00。',
        'provider-request-1', {'inputTokens':100, 'outputTokens':20})
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
            candidate_receipt['receiptDigest'], values['gateway'], DEPLOYMENT.id,
            CONTEXT.purpose, 'source-only', FUTURE)
        with pytest.raises(Rejected, match='FORBIDDEN'):
            core.record_model_invocation(
                WORKER, values['gateway'], authorization, 'f' * 64,
                '2026-11-01T00:00:00+00:00',
                '2026-11-01T00:00:01+00:00', 'RETURNED', 'forged',
                'forged-provider-request', {})
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
                receipt['receiptDigest'], values['gateway'], DEPLOYMENT.id,
                CONTEXT.purpose, 'source-only', FUTURE)
    finally:
        core.close()


def test_model_egress_uses_assignment_purpose_and_fixed_redaction_policy(tmp_path):
    core, client, values = prepare(tmp_path)
    try:
        receipt = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'],
            'quality-service-hours', 'policy-candidate-request',
            'policy-candidate-trace', client)
        for purpose, redaction in (
                ('other-purpose', 'source-only'),
                (CONTEXT.purpose, 'caller-selected-redaction')):
            with pytest.raises(
                    Rejected, match='EVALUATION_EGRESS_POLICY_MISMATCH'):
                core.authorize_model_egress(
                    MANAGER, f'bad-egress-{purpose}-{redaction}', 1,
                    values['assignment'], receipt['receiptDigest'],
                    values['gateway'], DEPLOYMENT.id, purpose, redaction, FUTURE)
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
            candidate_receipt['receiptDigest'], values['gateway'], DEPLOYMENT.id,
            CONTEXT.purpose, 'source-only', FUTURE)
        prepared = core.prepare_model_invocation(
            GATEWAY, values['gateway'], authorization, 'model-request-failed',
            'model-trace-failed', DEPLOYMENT.runtime_identity(ENVIRONMENT))
        failed = core.record_model_invocation(
            GATEWAY, values['gateway'], authorization,
            prepared['invocationAttemptDigest'], '2026-11-01T00:00:00+00:00',
            '2026-11-01T00:00:01+00:00', 'FAILED', None,
            'provider-request-failed', {'errorClass':'UPSTREAM_UNAVAILABLE'})
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

    try:
        core_client = CoreModelGatewayClient(
            core, GATEWAY, values['gateway'],
            DEPLOYMENT.runtime_identity(ENVIRONMENT))
        gateway = OpenJiuwenModelGateway(
            core_client, ENVIRONMENT, lambda unused: Model(), outbound.append)
        worker = CandidateEvaluationWorker(
            CandidateQueryClient(core, WORKER, values['assignment'],
                                 values['lease'], client),
            ModelAuthorizationClient(
                core, MANAGER, values['assignment'], values['gateway'],
                DEPLOYMENT.id, CONTEXT.purpose, 'source-only', FUTURE),
            gateway)
        runs = asyncio.run(worker.run(['quality-service-hours']))
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
            candidate['receiptDigest'], values['gateway'], DEPLOYMENT.id,
            CONTEXT.purpose, 'source-only', FUTURE)
        core_client = CoreModelGatewayClient(
            core, GATEWAY, values['gateway'],
            DEPLOYMENT.runtime_identity(ENVIRONMENT))
        gateway = OpenJiuwenModelGateway(
            core_client, ENVIRONMENT, lambda unused: Model())
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
            candidate['receiptDigest'], values['gateway'], DEPLOYMENT.id,
            CONTEXT.purpose, 'source-only', FUTURE)
        mismatched = {**DEPLOYMENT.runtime_identity(ENVIRONMENT),
                      'endpointOrigin':'https://attacker.example.test/v1'}
        with pytest.raises(Rejected, match='EVALUATION_MODEL_ENDPOINT_MISMATCH'):
            core.prepare_model_invocation(
                GATEWAY, values['gateway'], authorization, 'tampered-request',
                'tampered-trace', mismatched)
        core.activate_source(MANAGER, values['sourceDigest'], '2026-11-01', 'REVOKED')
        with pytest.raises(Rejected, match='SOURCE_SUPERSEDED_OR_REVOKED'):
            core.prepare_model_invocation(
                GATEWAY, values['gateway'], authorization, 'revoked-request',
                'revoked-trace', DEPLOYMENT.runtime_identity(ENVIRONMENT))
    finally:
        core.close()


def test_gateway_registration_rejects_endpoint_classification_spoof(tmp_path):
    core, _, _ = prepare(tmp_path)
    try:
        spoofed = {**DEPLOYMENT.registration(ENVIRONMENT), 'external':False}
        with pytest.raises(
                Rejected, match='EVALUATION_MODEL_ENDPOINT_CLASSIFICATION_MISMATCH'):
            core.register_model_gateway(
                MANAGER, 'spoofed-gateway', 1, GATEWAY.principal,
                DEPLOYMENT.gateway_build_digest, DEPLOYMENT.adapter_version,
                [spoofed], GATEWAY.authority, DEPLOYMENT.qualification_digest)
        unsafe = {**DEPLOYMENT.registration(ENVIRONMENT),
                  'endpointOrigin':'http://public.example.test/v1'}
        with pytest.raises(Rejected, match='EVALUATION_MODEL_ENDPOINT_INVALID'):
            core.register_model_gateway(
                MANAGER, 'unsafe-gateway', 1, GATEWAY.principal,
                DEPLOYMENT.gateway_build_digest, DEPLOYMENT.adapter_version,
                [unsafe], GATEWAY.authority, DEPLOYMENT.qualification_digest)
    finally:
        core.close()


def test_model_attempt_and_receipt_are_single_use(tmp_path):
    core, client, values = prepare(tmp_path)
    try:
        candidate = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'],
            'quality-service-hours', 'candidate-request-1',
            'candidate-trace-1', client)
        authorization = core.authorize_model_egress(
            MANAGER, 'single-use-egress', 1, values['assignment'],
            candidate['receiptDigest'], values['gateway'], DEPLOYMENT.id,
            CONTEXT.purpose, 'source-only', FUTURE)
        prepared = core.prepare_model_invocation(
            GATEWAY, values['gateway'], authorization, 'model-request-1',
            'model-trace-1', DEPLOYMENT.runtime_identity(ENVIRONMENT))
        with pytest.raises(Rejected, match='EVALUATION_MODEL_INVOCATION_REPLAYED'):
            core.prepare_model_invocation(
                GATEWAY, values['gateway'], authorization, 'model-request-2',
                'model-trace-2', DEPLOYMENT.runtime_identity(ENVIRONMENT))
        receipt = core.record_model_invocation(
            GATEWAY, values['gateway'], authorization,
            prepared['invocationAttemptDigest'],
            '2026-11-01T00:00:00+00:00', '2026-11-01T00:00:01+00:00',
            'RETURNED', '根据第一条，服务时间为09:00至17:00。',
            'provider-request-1', {})
        assert receipt
        with pytest.raises(Rejected, match='EVALUATION_MODEL_INVOCATION_REPLAYED'):
            core.record_model_invocation(
                GATEWAY, values['gateway'], authorization,
                prepared['invocationAttemptDigest'],
                '2026-11-01T00:00:00+00:00', '2026-11-01T00:00:01+00:00',
                'RETURNED', 'duplicate', 'provider-request-2', {})
    finally:
        core.close()


def test_runtime_evidence_requires_lease_bound_worker_build(tmp_path):
    core, client, values = prepare(tmp_path)
    try:
        candidate, _, model_receipt = run_candidate(core, client, values)
        with pytest.raises(Rejected, match='QUALITY_RUNTIME_BINDING_MISMATCH'):
            core.register_factory_evaluation_runtime_evidence(
                MANAGER, values['assignment'], values['lease'], 'f' * 64,
                '3.12', '0.1.17.post1', [{
                    'caseId':'quality-service-hours',
                    'candidateReceiptDigest':candidate['receiptDigest'],
                    'modelReceiptDigest':model_receipt,
                }])
    finally:
        core.close()


def test_runtime_evidence_rejects_revoked_worker_lease(tmp_path):
    core, client, values = prepare(tmp_path)
    try:
        candidate, _, model_receipt = run_candidate(core, client, values)
        core.revoke_evaluation_lease(
            MANAGER, values['lease'], 'runtime-lease-revocation')
        with pytest.raises(Rejected, match='EVALUATION_LEASE_REVOKED'):
            core.register_factory_evaluation_runtime_evidence(
                MANAGER, values['assignment'], values['lease'], 'a' * 64,
                '3.12', '0.1.17.post1', [{
                    'caseId':'quality-service-hours',
                    'candidateReceiptDigest':candidate['receiptDigest'],
                    'modelReceiptDigest':model_receipt,
                }])
    finally:
        core.close()


def test_endpoint_mismatch_is_rejected_before_model_or_observer(tmp_path):
    core, client, values = prepare(tmp_path)
    calls, outbound = [], []

    class Model:
        async def invoke(self, messages, **kwargs):
            calls.append((messages, kwargs))
            raise AssertionError('model must not be called')

    try:
        candidate = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'],
            'quality-service-hours', 'candidate-request-1',
            'candidate-trace-1', client)
        authorization = core.authorize_model_egress(
            MANAGER, 'mismatch-egress', 1, values['assignment'],
            candidate['receiptDigest'], values['gateway'], DEPLOYMENT.id,
            CONTEXT.purpose, 'source-only', FUTURE)
        mismatched = {**DEPLOYMENT.runtime_identity(ENVIRONMENT),
                      'modelRef':'other-model'}
        gateway = OpenJiuwenModelGateway(
            CoreModelGatewayClient(
                core, GATEWAY, values['gateway'], mismatched),
            ENVIRONMENT, lambda unused: Model(), outbound.append)
        with pytest.raises(Rejected, match='EVALUATION_MODEL_ENDPOINT_MISMATCH'):
            asyncio.run(gateway.invoke(
                authorization, 'mismatch-request', 'mismatch-trace'))
        assert calls == []
        assert outbound == []
    finally:
        core.close()


@pytest.mark.parametrize(('error', 'content', 'expected'), [
    (ValueError('private sdk detail'), None,
     {'stage':'SDK_INVOCATION', 'code':'SDK_PARAMETER_OR_RESPONSE_INVALID'}),
    (None, '', {'stage':'RESPONSE_VALIDATION', 'code':'MODEL_RESPONSE_EMPTY'}),
    (None, 'x' * 11,
     {'stage':'RESPONSE_VALIDATION', 'code':'MODEL_RESPONSE_TOO_LARGE'}),
    (TimeoutError('private timeout detail'), None,
     {'stage':'UPSTREAM', 'code':'UPSTREAM_TIMEOUT'}),
    (ConnectionError('private endpoint detail'), None,
     {'stage':'UPSTREAM', 'code':'UPSTREAM_DISCONNECTED'}),
    (APIStatusError('private service detail'), None,
     {'stage':'UPSTREAM', 'code':'UPSTREAM_SERVICE_ERROR'}),
    (RuntimeError('private runtime detail'), None,
     {'stage':'RUNTIME', 'code':'RUNTIME_UNCLASSIFIED'}),
])
def test_gateway_records_only_bounded_failure_classification(error, content,
                                                              expected):
    class CoreClient:
        def __init__(self):
            self.records = []

        def prepare(self, authorization, request_id, trace_id):
            return {'invocationAttemptDigest':'a' * 64,
                    'requestPayloadDigest':'b' * 64,
                    'messages':[{'role':'user', 'content':'bounded'}],
                    'model':'deepseek-v4-flash', 'temperature':0,
                    'maxAnswerCharacters':10}

        def record(self, *args):
            self.records.append(args)
            return 'receipt'

    class Model:
        async def invoke(self, messages, **kwargs):
            if error:
                raise error
            return SimpleNamespace(content=content, usage_metadata=None,
                                   metadata={})

    core = CoreClient()
    gateway = OpenJiuwenModelGateway(
        core, ENVIRONMENT, lambda unused:Model())
    with pytest.raises(Exception):
        asyncio.run(gateway.invoke('authorization', 'request', 'trace'))
    assert len(core.records) == 1
    assert core.records[0][-1] == expected
    assert core.records[0][-2] == {}
    assert 'private' not in repr(core.records[0])


def test_gateway_rejects_invalid_prepared_request_with_safe_receipt():
    class CoreClient:
        def __init__(self):
            self.records = []

        def prepare(self, authorization, request_id, trace_id):
            return {'invocationAttemptDigest':'a' * 64,
                    'requestPayloadDigest':'b' * 64, 'messages':'invalid',
                    'model':'deepseek-v4-flash', 'temperature':0,
                    'maxAnswerCharacters':10}

        def record(self, *args):
            self.records.append(args)

    class Model:
        async def invoke(self, messages, **kwargs):
            raise AssertionError('invalid prepared request must not reach model')

    core = CoreClient()
    gateway = OpenJiuwenModelGateway(core, ENVIRONMENT, lambda unused:Model())
    with pytest.raises(RuntimeError, match='REQUEST_OR_CONFIG_INVALID'):
        asyncio.run(gateway.invoke('authorization', 'request', 'trace'))
    assert core.records[0][-1] == {
        'stage':'REQUEST_VALIDATION', 'code':'REQUEST_OR_CONFIG_INVALID'}


def test_failed_gateway_receipt_is_safe_and_attempt_cannot_be_reused(tmp_path):
    core, client, values = prepare(tmp_path)

    class Model:
        async def invoke(self, messages, **kwargs):
            raise TimeoutError('private provider timeout')

    try:
        candidate = core.query_document_candidate_for_evaluation(
            WORKER, values['assignment'], values['lease'],
            'quality-service-hours', 'failure-candidate-request',
            'failure-candidate-trace', client)
        authorization = core.authorize_model_egress(
            MANAGER, 'failure-egress', 1, values['assignment'],
            candidate['receiptDigest'], values['gateway'], DEPLOYMENT.id,
            CONTEXT.purpose, 'source-only', FUTURE)
        gateway = OpenJiuwenModelGateway(
            CoreModelGatewayClient(core, GATEWAY, values['gateway'],
                                   DEPLOYMENT.runtime_identity(ENVIRONMENT)),
            ENVIRONMENT, lambda unused:Model())
        with pytest.raises(TimeoutError):
            asyncio.run(gateway.invoke(
                authorization, 'failure-request', 'failure-trace'))
        row = core.db.execute(
            "SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC LIMIT 1",
            ('model-invocation-receipt',)).fetchone()
        receipt = json.loads(row[0])
        assert receipt['outcome'] == 'FAILED'
        assert receipt['failure'] == {
            'stage':'UPSTREAM', 'code':'UPSTREAM_TIMEOUT'}
        assert receipt['usage'] == {}
        assert 'private provider timeout' not in row[0]
        with pytest.raises(Rejected, match='EVALUATION_MODEL_INVOCATION_REPLAYED'):
            asyncio.run(gateway.invoke(
                authorization, 'failure-retry', 'failure-retry-trace'))
    finally:
        core.close()
