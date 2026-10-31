"""Read-only release projection; no catalog store, publication or authority writes."""
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from lxml import html

from knowledge_core.contracts import Rejected, digest
from m2.history_runtime import ReadOnlyDocumentCore, SCHEMA_SHA256 as HISTORY_SHA
from m2.runtime_protocol import CONTRACT_SHA256 as QUERY_SHA

SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'contracts/runtime/knowledge-products-v0.1.schema.json'
SCHEMA = json.loads(SCHEMA_PATH.read_bytes())
SCHEMA_SHA256 = sha256(SCHEMA_PATH.read_bytes()).hexdigest()
if SCHEMA_SHA256 != '0b671ae3de0dcb04e0614a9bed80ee38b7cd4672fb9db9df064aabe25f0a7e4e':
    raise RuntimeError('FROZEN_DISCOVERY_SCHEMA_CHANGED')


def validate(kind, body, error='DISCOVERY_INTEGRITY_FAILED'):
    validator = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/' + kind}, format_checker=FormatChecker())
    if not validator.is_valid(body):
        raise Rejected(error)


def describe(core, actor, context, product, manifest_digest, connection_ref):
    """Caller must establish Host discovery authority before requesting this projection."""
    _, manifest, index, _ = core._query_binding(actor, product, manifest_digest, context)
    candidate, recipe, artifacts, _ = core._document_parts(actor, manifest['candidateDigest'])
    core._document_valid(actor, manifest['candidateDigest'], manifest['validationDigest'])
    approval = core._get(actor, manifest['approvalDigest'], 'document-approval')
    source = core._source_access(actor, manifest['sourceDigest'])
    if (manifest['productId'] != product or manifest['id'] != product
            or candidate['productId'] != product or recipe['productId'] != product
            or candidate['indexDigest'] != manifest['indexDigest']
            or manifest['sourceDigest'] != index['sourceDigest']
            or approval['candidateDigest'] != manifest['candidateDigest']
            or approval['validationDigest'] != manifest['validationDigest']
            or approval['decision'] != 'ISOLATED_TEST_APPROVAL'
            or manifest['mode'] != 'M2_ISOLATED_DOCUMENT'
            or recipe['processes'] != ['document'] or not artifacts
            or any(a['kind'] != 'evidence' or a['ruleSetDigest'] is not None for a in artifacts)):
        raise Rejected('DISCOVERY_INTEGRITY_FAILED')
    title = ' '.join(html.fromstring(index['originalHtml']).xpath('//title/text()')).strip()
    name = title if 0 < len(title) <= 256 else product
    source_permission = {'resource': 'source:' + source['id'], 'action': 'source_read'}
    descriptor = {
        'schemaVersion': 'knowledge-product-release.v0.1', 'productId': product,
        'name': name, 'nameOrigin': 'PINNED_SOURCE_TITLE' if name == title else 'PRODUCT_ID_FALLBACK',
        'productType': 'DOCUMENT_EVIDENCE', 'version': manifest['revision'],
        'manifestDigest': manifest_digest, 'publication': {
            'state': 'PUBLISHED', 'mode': manifest['mode'], 'approvalDecision': approval['decision'],
            'productionAuthorized': False},
        'versionPolicy': 'PINNED', 'connectionRef': connection_ref,
        'capabilities': ['knowledge.evidence.search'],
        'applicability': {'combine': 'ALL', 'scopes': list({digest(a['scope']): a['scope'] for a in artifacts}.values())},
        'permissions': {
            'query': [{'resource': 'product:' + product, 'action': 'consume'}, source_permission],
            'history': [{'resource': 'product:' + product, 'action': 'history'}, source_permission],
            'crossPrincipalHistory': 'HOST_EXACT_RECEIPT_AND_CORE_RECEIPT_HISTORY_REQUIRED',
            'authority': 'CURRENT_HOST_AND_CORE_REQUIRED'},
        'source': {'sourceId': source['id'], 'sourceRevision': source['revision'],
            'sourceDigest': manifest['sourceDigest'], 'contentDigest': source['contentDigest'],
            'originalDigest': index['originalDigest'], 'anchorDigest': index['bridgeDigest']},
        'releaseEvidence': {key: manifest[key] for key in
            ('candidateDigest', 'validationDigest', 'approvalDigest', 'indexDigest')},
        'protocols': {
            'query': {'schemaVersion': 'knowledge-query.v0.1', 'method': 'POST', 'path': '/query', 'schemaDigest': QUERY_SHA},
            'session': {'schemaVersion': 'knowledge-session-check.v0.1', 'method': 'POST', 'path': '/session', 'schemaDigest': QUERY_SHA},
            'history': {'schemaVersion': 'knowledge-history.v0.1', 'method': 'POST', 'path': '/history/read', 'schemaDigest': HISTORY_SHA}}}
    validate('release', descriptor)
    return {'descriptorDigest': digest(descriptor), 'descriptor': descriptor}


def read_release(database, actor, context, product, manifest, connection_ref):
    """Operator-side export using an already authenticated Actor; not a public API."""
    core = ReadOnlyDocumentCore(database)
    try:
        with core.tx():
            return describe(core, actor, context, product, manifest, connection_ref)
    finally:
        core.close()
