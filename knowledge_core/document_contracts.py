"""Additive M2 document contracts. M0 formats and rule approval are unchanged."""
from jsonschema import Draft202012Validator

from .contracts import (BOOL, HASH, ID, REV, STR, Rejected, arr, canonical,
                        digest, enum, obj, versioned)

CHUNK = obj({'id': ID, 'text': STR, 'textDigest': HASH, 'clauses': arr(STR)})
INDEX = obj({'datasetId': ID, 'documentId': ID, 'buildId': ID,
             'engineIdentity': STR, 'embeddingIdentity': STR, 'chunks': arr(CHUNK, 1)})
CASE = obj({'question': STR, 'expectedClause': STR})
TIMESTAMP = {'type': 'string', 'minLength': 20, 'maxLength': 64}
LONG_STR = {'type': 'string', 'minLength': 1, 'maxLength': 100000}
BUSINESS_CONTEXT = obj({'business_date': STR, 'region': ID, 'institution': ID,
                        'product': ID, 'purpose': ID, 'timezone': STR})
ANSWER_EVALUATION = obj({
    'schemaVersion': enum('document-answer-evaluation.v0.1',
                          'document-answer-evaluation.v0.2'),
    'candidateDigest': HASH, 'profileDigest': HASH, 'testSetDigest': HASH,
    'retrievalEvaluationDigest': HASH, 'runtimeEvidenceDigest': HASH,
    'execution': enum('CORE_CORRELATED_HARNESS_ARCHIVE'),
    'modelIdentity': {'type': 'object'}, 'cases': arr({'type': 'object'}, 1),
    'metricsBps': {'type': 'object'}})
QUALITY_ADMISSION = versioned('document-quality-admission', {
    'candidateDigest': HASH, 'sourceDigest': HASH, 'indexDigest': HASH,
    'profileDigest': HASH, 'testSetDigest': HASH, 'retrievalEvaluationDigest': HASH,
    'answerEvaluationDigest': HASH, 'decision': enum('PASS', 'REJECT'),
    'checks': {'type': 'object'}, 'gateDigest': HASH})
SCHEMAS = {
    'document-quality-profile': versioned('document-quality-profile', {
        'id': ID, 'revision': REV, 'config': {'type': 'object'}}),
    'document-quality-test-set': versioned('document-quality-test-set', {
        'id': ID, 'revision': REV, 'candidateDigest': HASH, 'testSet': {'type': 'object'}}),
    'document-retrieval-evaluation': versioned('document-retrieval-evaluation', {
        'candidateDigest': HASH, 'profileDigest': HASH, 'testSetDigest': HASH,
        'execution': enum('CORE_EXECUTED'), 'report': {'type': 'object'}}),
    'document-answer-runtime-evidence': obj({
        'schemaVersion': enum('document-answer-runtime-evidence.v0.1',
                              'document-answer-runtime-evidence.v0.2'),
        'candidateDigest': HASH, 'testSetDigest': HASH, 'buildId': ID, 'instanceId': ID,
        'installationLockDigest': HASH, 'manifestDigest': HASH,
        'modelIdentity': {'type': 'object'}, 'cases': arr({'type': 'object'}, 1),
        'stoppedAt': STR, 'verification': enum('CORE_CORRELATED_HARNESS_ARCHIVE')}),
    'document-answer-evaluation': {'oneOf': [ANSWER_EVALUATION, obj({
        'schemaVersion': enum('document-answer-evaluation.v0.3'),
        'candidateDigest': HASH, 'profileDigest': HASH, 'testSetDigest': HASH,
        'retrievalEvaluationDigest': HASH, 'runtimeEvidenceDigest': HASH,
        'execution': enum('CORE_CORRELATED_HARNESS_ARCHIVE',
                          'CORE_CORRELATED_FACTORY_WORKER'),
        'evidenceAuthority': enum('HARNESS_ARCHIVE', 'FACTORY_WORKER'),
        'modelIdentity': {'type': 'object'}, 'cases': arr({'type': 'object'}, 1),
        'metricsBps': {'type': 'object'}})]},
    'document-quality-admission': {'oneOf': [QUALITY_ADMISSION, obj({
        'schemaVersion': enum('document-quality-admission.v0.2'),
        'candidateDigest': HASH, 'sourceDigest': HASH, 'indexDigest': HASH,
        'profileDigest': HASH, 'testSetDigest': HASH, 'retrievalEvaluationDigest': HASH,
        'answerEvaluationDigest': HASH, 'decision': enum('PASS', 'REJECT'),
        'answerEvidenceAuthority': enum('HARNESS_ARCHIVE', 'FACTORY_WORKER'),
        'qualityGateVersion': enum('document-quality-gate.v0.2'),
        'checks': {'type': 'object'}, 'gateDigest': HASH})]},
    'document-source-classification': versioned('document-source-classification', {
        'id': ID, 'revision': REV, 'sourceDigest': HASH,
        'classification': enum('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED'),
        'externalModelAllowed': BOOL, 'allowedProviders': arr(ID),
        'allowedRegions': arr(ID), 'allowedExecutionZones': arr(ID, 1)}),
    'document-evaluation-prompt-template': versioned(
        'document-evaluation-prompt-template', {
            'id': ID, 'revision': REV, 'systemInstruction': STR,
            'answerInstruction': STR,
            'evidenceFormat': enum('NUMBERED_CLAUSE_QUOTES'),
            'maxEvidenceItems': {'type': 'integer', 'minimum': 1, 'maximum': 3},
            'maxAnswerCharacters': {'type': 'integer', 'minimum': 1,
                                    'maximum': 100000}}),
    'document-evaluation-assignment': versioned('document-evaluation-assignment', {
        'id': ID, 'revision': REV, 'candidateDigest': HASH, 'sourceDigest': HASH,
        'indexDigest': HASH, 'testSetDigest': HASH, 'profileDigest': HASH,
        'retrievalEvaluationDigest': HASH, 'classificationDigest': HASH,
        'modelSelectionDigest': HASH, 'promptTemplateDigest': HASH,
        'businessContext': BUSINESS_CONTEXT, 'caseIds': arr(ID, 1),
        'createdAt': TIMESTAMP, 'expiresAt': TIMESTAMP, 'state': enum('READY')}),
    'knowledge-evaluation-lease': versioned('knowledge-evaluation-lease', {
        'id': ID, 'revision': REV, 'assignmentDigest': HASH, 'tenant': ID,
        'principal': ID, 'workerIdentity': ID, 'caseIds': arr(ID, 1),
        'maxCalls': {'type': 'integer', 'minimum': 1, 'maximum': 1000},
        'issuedAt': TIMESTAMP, 'expiresAt': TIMESTAMP, 'nonce': ID,
        'operation': enum('evaluation.evidence.read')}),
    'knowledge-evaluation-lease-revocation': versioned(
        'knowledge-evaluation-lease-revocation', {
            'id': ID, 'revision': REV, 'leaseDigest': HASH,
            'revokedAt': TIMESTAMP, 'authorityRef': STR}),
    'document-candidate-query-receipt': obj({
        'schemaVersion': enum('document-candidate-query-receipt.v0.1'),
        'assignmentDigest': HASH, 'leaseDigest': HASH, 'candidateDigest': HASH,
        'sourceDigest': HASH, 'indexDigest': HASH, 'testSetDigest': HASH,
        'profileDigest': HASH, 'caseId': ID, 'question': STR,
        'requestId': ID, 'traceId': ID, 'principal': ID,
        'policyDigest': HASH, 'sourceActivationDigest': HASH,
        'businessContext': BUSINESS_CONTEXT,
        'result': obj({'decision': enum('EVIDENCE_FOUND', 'EVIDENCE_NOT_FOUND'),
                       'evidence': arr({'type': 'object'}, 0, 3)}),
        'retrievalTraceDigest': HASH, 'createdAt': TIMESTAMP}),
    'model-gateway-registration': versioned('model-gateway-registration', {
        'id': ID, 'revision': REV, 'gatewayPrincipal': ID, 'buildDigest': HASH,
        'adapterVersion': STR, 'openJiuwenVersion': enum('0.1.17.post1'),
        'allowedProviders': arr(ID, 1), 'allowedModelRefs': arr(ID, 1),
        'allowedRegions': arr(ID, 1), 'receiptAuthority': STR,
        'qualificationDigest': HASH, 'status': enum('QUALIFIED')}),
    'model-egress-authorization': versioned('model-egress-authorization', {
        'id': ID, 'revision': REV, 'assignmentDigest': HASH, 'caseId': ID,
        'candidateReceiptDigest': HASH, 'classificationDigest': HASH,
        'promptDigest': HASH, 'evidenceDigest': HASH, 'provider': ID,
        'modelRef': ID, 'modelConfigDigest': HASH, 'region': ID,
        'purpose': ID, 'executionZone': ID, 'external': BOOL,
        'redactionProfile': ID, 'issuedAt': TIMESTAMP, 'expiresAt': TIMESTAMP,
        'decision': enum('ALLOW')}),
    'model-answer-archive': versioned('model-answer-archive', {
        'id': ID, 'revision': REV, 'assignmentDigest': HASH, 'caseId': ID,
        'requestId': ID, 'traceId': ID, 'response': LONG_STR,
        'responseDigest': HASH, 'createdAt': TIMESTAMP}),
    'model-invocation-receipt': obj({
        'schemaVersion': enum('model-invocation-receipt.v0.1'),
        'assignmentDigest': HASH, 'caseId': ID, 'egressAuthorizationDigest': HASH,
        'gatewayRegistrationDigest': HASH, 'gatewayPrincipal': ID,
        'provider': ID, 'modelRef': ID, 'modelConfigDigest': HASH,
        'promptDigest': HASH, 'evidenceDigest': HASH, 'requestId': ID, 'traceId': ID,
        'requestPayloadDigest': HASH,
        'startedAt': TIMESTAMP, 'endedAt': TIMESTAMP,
        'outcome': enum('RETURNED', 'FAILED'),
        'answerArchiveDigest': {'anyOf': [HASH, {'type': 'null'}]},
        'responseDigest': {'anyOf': [HASH, {'type': 'null'}]},
        'providerRequestRef': STR,
        'usage': {'type': 'object'}}),
    'document-factory-evaluation-runtime-evidence': obj({
        'schemaVersion': enum('document-factory-evaluation-runtime-evidence.v0.1'),
        'candidateDigest': HASH, 'testSetDigest': HASH, 'assignmentDigest': HASH,
        'leaseDigest': HASH, 'workerBuildDigest': HASH,
        'pythonVersion': enum('3.12'), 'openJiuwenVersion': enum('0.1.17.post1'),
        'modelIdentity': {'type': 'object'}, 'cases': arr({'type': 'object'}, 1),
        'verification': enum('CORE_CORRELATED_FACTORY_WORKER'),
        'createdAt': TIMESTAMP}),
    'document-quality-manifest-admission': versioned('document-quality-manifest-admission', {
        'id': ID, 'revision': REV, 'manifestDigest': HASH,
        'qualityAdmissionDigest': HASH, 'candidateDigest': HASH}),
    'document-index': versioned('document-index', {
        'sourceDigest': HASH, 'originalHtml': {'type': 'string', 'maxLength': 1000000},
        'originalDigest': HASH, 'bridge': {'type': 'object'}, 'bridgeDigest': HASH,
        'index': INDEX, 'clauses': arr(obj({'clause': STR, 'text': STR}), 1)}),
    'document-candidate': versioned('document-candidate', {
        'productId': ID, 'coreCandidateDigest': HASH, 'indexDigest': HASH,
        'tests': arr(CASE, 1, 30)}),
    'document-validation': versioned('document-validation', {
        'candidateDigest': HASH, 'coreValidationDigest': HASH, 'passed': BOOL,
        'results': arr(obj({'question': STR, 'expectedClause': STR,
                            'actualClauses': arr(STR), 'passed': BOOL, 'error': {'type': ['string','null']}}), 1, 30)}),
    'document-approval': versioned('document-approval', {
        'candidateDigest': HASH, 'validationDigest': HASH, 'actor': ID,
        'authorityRef': STR, 'decision': enum('ISOLATED_TEST_APPROVAL'), 'reason': STR}),
    'document-manifest': versioned('document-manifest', {
        'id': ID, 'revision': REV, 'productId': ID, 'candidateDigest': HASH,
        'validationDigest': HASH, 'approvalDigest': HASH, 'indexDigest': HASH,
        'sourceDigest': HASH, 'mode': enum('M2_ISOLATED_DOCUMENT')}),
    'document-binding': versioned('document-binding', {
        'productId': ID, 'revision': REV, 'manifestDigest': HASH, 'versionPolicy': enum('PINNED')}),
    'document-receipt': versioned('document-receipt', {
        'requestId': ID, 'traceId': ID, 'principal': ID, 'productId': ID,
        'manifestDigest': HASH, 'indexDigest': HASH, 'sourceDigest': HASH,
        'bindingDigest': HASH, 'policyDigest': HASH, 'question': STR,
        'hostAuthority': STR, 'businessContextSource': STR,
        'host': {'type':'object'}, 'result': {'type':'object'}, 'createdAt': STR,
        'mode': enum('M2_ISOLATED_DOCUMENT')})
}


def validate(kind, value):
    if len(canonical(value).encode()) > 2_000_000:
        raise Rejected('CONTRACT_TOO_LARGE')
    if kind not in SCHEMAS or not Draft202012Validator(SCHEMAS[kind]).is_valid(value):
        raise Rejected('DOCUMENT_SCHEMA_INVALID', kind)
    return digest(value)
