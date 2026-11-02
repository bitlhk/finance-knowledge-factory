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
if SCHEMA_SHA256 != 'f43326b801cbb4c87ec7bde4bd10ff48aef34a6f418dfb533c70f7666a056a52':
    raise RuntimeError('FROZEN_DISCOVERY_SCHEMA_CHANGED')


def validate(kind, body, error='DISCOVERY_INTEGRITY_FAILED'):
    validator = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/' + kind}, format_checker=FormatChecker())
    if not validator.is_valid(body):
        raise Rejected(error)


def _business_binding(index):
    tree = html.fromstring(index['originalHtml'])
    values = tree.xpath(
        '//script[@id="knowledge-business-binding" and @type="application/json"]/text()')
    if not values:
        return None
    if len(values) != 1:
        raise Rejected('DISCOVERY_INTEGRITY_FAILED')
    try:
        binding = json.loads(values[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        raise Rejected('DISCOVERY_INTEGRITY_FAILED') from None
    if (not isinstance(binding, dict)
            or binding.get('schemaVersion') != 'product-knowledge-binding.v0.1'
            or binding.get('knowledgeKind') != 'PRODUCT_SPECIFIC'):
        raise Rejected('DISCOVERY_INTEGRITY_FAILED')
    return binding


def describe(core, actor, context, product, manifest_digest, connection_ref):
    """Caller must establish Host discovery authority before requesting this projection."""
    _, manifest, index, _ = core._query_binding(actor, product, manifest_digest, context)
    candidate, recipe, artifacts, _ = core._document_parts(actor, manifest['candidateDigest'])
    core._document_valid(actor, manifest['candidateDigest'], manifest['validationDigest'])
    approval = core._get(actor, manifest['approvalDigest'], 'document-approval')
    source = core._source_access(actor, manifest['sourceDigest'])
    legacy_approval = (approval.get('schemaVersion') == 'document-approval.v0.1'
                       and approval.get('decision') == 'ISOLATED_TEST_APPROVAL')
    quality_approval = (approval.get('schemaVersion') == 'document-approval.v0.3'
                        and approval.get('decision') == 'QUALITY_RELEASE_APPROVAL')
    if quality_approval:
        row = core.db.execute(
            "SELECT digest FROM identities WHERE tenant=? AND kind=? AND name=? AND revision=1",
            (actor.tenant, 'document-quality-manifest-admission', manifest_digest)).fetchone()
        if not row:
            raise Rejected('DISCOVERY_INTEGRITY_FAILED')
        link = core._get(actor, row[0], 'document-quality-manifest-admission')
        admission = core._get(actor, link['qualityAdmissionDigest'],
                              'document-quality-admission')
        quality_approval = (
            link.get('manifestDigest') == manifest_digest
            and link.get('candidateDigest') == manifest['candidateDigest']
            and approval.get('qualityAdmissionDigest') == link.get('qualityAdmissionDigest')
            and approval.get('candidateDigest') == manifest['candidateDigest']
            and approval.get('validationDigest') == manifest['validationDigest']
            and approval.get('sourceDigest') == manifest['sourceDigest']
            and approval.get('indexDigest') == manifest['indexDigest']
            and admission.get('decision') == 'PASS'
            and admission.get('candidateDigest') == manifest['candidateDigest']
            and admission.get('sourceDigest') == manifest['sourceDigest']
            and admission.get('indexDigest') == manifest['indexDigest'])
    if (manifest['productId'] != product or manifest['id'] != product
            or candidate['productId'] != product or recipe['productId'] != product
            or candidate['indexDigest'] != manifest['indexDigest']
            or manifest['sourceDigest'] != index['sourceDigest']
            or approval['candidateDigest'] != manifest['candidateDigest']
            or approval['validationDigest'] != manifest['validationDigest']
            or not (legacy_approval or quality_approval)
            or manifest['mode'] != 'M2_ISOLATED_DOCUMENT'
            or recipe['processes'] != ['document'] or not artifacts
            or any(a['kind'] != 'evidence' or a['ruleSetDigest'] is not None for a in artifacts)):
        raise Rejected('DISCOVERY_INTEGRITY_FAILED')
    title = ' '.join(html.fromstring(index['originalHtml']).xpath('//title/text()')).strip()
    name = title if 0 < len(title) <= 256 else product
    source_permission = {'resource': 'source:' + source['id'], 'action': 'source_read'}
    business_binding = _business_binding(index)
    descriptor = {
        'schemaVersion': ('knowledge-product-release.v0.2' if business_binding
                          else 'knowledge-product-release.v0.1'), 'productId': product,
        'name': name, 'nameOrigin': 'PINNED_SOURCE_TITLE' if name == title else 'PRODUCT_ID_FALLBACK',
        'productType': 'DOCUMENT_EVIDENCE', 'version': manifest['revision'],
        'manifestDigest': manifest_digest, 'publication': {
            # v0.1 consumers use this value only as the isolated-publication marker.
            # Quality approval is verified above and remains linked inside Core.
            'state': 'PUBLISHED', 'mode': manifest['mode'], 'approvalDecision': 'ISOLATED_TEST_APPROVAL',
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
    if business_binding is not None:
        descriptor['businessBinding'] = business_binding
        descriptor['businessBindingDigest'] = digest(business_binding)
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
