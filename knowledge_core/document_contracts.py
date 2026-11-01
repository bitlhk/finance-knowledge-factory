"""Additive M2 document contracts. M0 formats and rule approval are unchanged."""
from jsonschema import Draft202012Validator

from .contracts import (BOOL, HASH, ID, REV, STR, Rejected, arr, canonical,
                        digest, enum, obj, versioned)

CHUNK = obj({'id': ID, 'text': STR, 'textDigest': HASH, 'clauses': arr(STR)})
INDEX = obj({'datasetId': ID, 'documentId': ID, 'buildId': ID,
             'engineIdentity': STR, 'embeddingIdentity': STR, 'chunks': arr(CHUNK, 1)})
CASE = obj({'question': STR, 'expectedClause': STR})
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
    'document-answer-evaluation': obj({
        'schemaVersion': enum('document-answer-evaluation.v0.1',
                              'document-answer-evaluation.v0.2'),
        'candidateDigest': HASH, 'profileDigest': HASH, 'testSetDigest': HASH,
        'retrievalEvaluationDigest': HASH, 'runtimeEvidenceDigest': HASH,
        'execution': enum('CORE_CORRELATED_HARNESS_ARCHIVE'), 'modelIdentity': {'type': 'object'},
        'cases': arr({'type': 'object'}, 1), 'metricsBps': {'type': 'object'}}),
    'document-quality-admission': versioned('document-quality-admission', {
        'candidateDigest': HASH, 'sourceDigest': HASH, 'indexDigest': HASH,
        'profileDigest': HASH, 'testSetDigest': HASH, 'retrievalEvaluationDigest': HASH,
        'answerEvaluationDigest': HASH, 'decision': enum('PASS', 'REJECT'),
        'checks': {'type': 'object'}, 'gateDigest': HASH}),
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
