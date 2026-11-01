"""Read-only replay of saved Core evidence under independent Host view leases."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat

from jsonschema import Draft202012Validator, FormatChecker

from knowledge_core.contracts import Rejected, digest, text_digest
from knowledge_core.core import Actor
from knowledge_core.documents import DocumentCore
from knowledge_core.evidence.anchor_bridge import verify_bridge

SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'contracts/runtime/knowledge-history-v0.1.proposed.schema.json'
SCHEMA_SHA256 = '114397ec532e40b84975e5884457ed1de63b45c71a05652c7e8ed5c3f1f3c3c6'
if sha256(SCHEMA_PATH.read_bytes()).hexdigest() != SCHEMA_SHA256:
    raise RuntimeError('FROZEN_HISTORY_SCHEMA_CHANGED')
SCHEMA = json.loads(SCHEMA_PATH.read_bytes())
MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 512 * 1024
ERRORS = {'HISTORY_REQUEST_INVALID': 400, 'HISTORY_AUTH_REQUIRED': 403,
          'HISTORY_FORBIDDEN': 403, 'HISTORY_REFERENCE_MISMATCH': 409,
          'HISTORY_INTEGRITY_FAILED': 409, 'HISTORY_RESPONSE_LIMIT': 413,
          'HISTORY_UNAVAILABLE': 503}


def validate(kind, value, error):
    validator = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/' + kind}, format_checker=FormatChecker())
    if not validator.is_valid(value):
        raise Rejected(error)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_KEY')
        result[key] = value
    return result


def decode(raw):
    def invalid(_):
        raise ValueError('INVALID_NUMBER')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def private_read(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('PRIVATE_PATH_REQUIRED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()):
            raise ValueError('PRIVATE_FILE_REQUIRED')
        raw = stream.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError('PRIVATE_FILE_TOO_LARGE')
        return raw


@dataclass(frozen=True)
class HistoryLease:
    actor: Actor
    product: str
    manifest: str
    receipts: tuple
    session: str
    policy_digest: str
    lease_digest: str


class HistoryLeases:
    """Verifier only. No issuance, refresh, grant or policy-writing operations."""
    def __init__(self, authority):
        self.authority = Path(authority)

    def __call__(self, token):
        try:
            if not isinstance(token, str) or not 32 <= len(token) <= 4096:
                raise ValueError()
            raw = private_read(self.authority)
            policy = decode(raw)
            validate('hostAuthority', policy, 'HISTORY_AUTH_REQUIRED')
            now = datetime.now(timezone.utc)
            expiry = datetime.fromisoformat(policy['expiresAt'].replace('Z', '+00:00'))
            if not policy['enabled'] or expiry <= now:
                raise ValueError()
            directory = Path(policy['leaseDirectory'])
            info = directory.lstat()
            if (not directory.is_absolute() or directory.resolve() != directory
                    or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
                    or info.st_uid != os.geteuid()):
                raise ValueError()
            lease_raw = private_read(directory / (sha256(token.encode()).hexdigest() + '.json'))
            lease = decode(lease_raw)
            validate('hostLease', lease, 'HISTORY_AUTH_REQUIRED')
            end = datetime.fromisoformat(lease['expiresAt'].replace('Z', '+00:00'))
            if (lease['policyDigest'] != sha256(raw).hexdigest()
                    or lease['ownerRef'] != policy['ownerRef'] or not now < end <= expiry
                    or (end - now).total_seconds() > 900):
                raise ValueError()
            return HistoryLease(Actor(policy['tenant'], policy['principalId'], policy['authority']),
                policy['productId'], policy['manifest'], tuple(policy['allowedReceiptDigests']),
                lease['viewerSessionRef'], sha256(raw).hexdigest(), sha256(lease_raw).hexdigest())
        except (OSError, ValueError, TypeError, KeyError, Rejected):
            raise Rejected('HISTORY_AUTH_REQUIRED') from None


class ReadOnlyDocumentCore(DocumentCore):
    """Reuse replay permissions, without Core initialization DDL or write locks."""
    def __init__(self, database):
        self.db = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro',
                                  uri=True, isolation_level=None, timeout=5)
        self.db.execute('PRAGMA query_only=ON')
        self.execution_count = 0

    @contextmanager
    def tx(self):
        self.db.execute('BEGIN')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise


def authorized_replay(core, lease, receipt_digest):
    if receipt_digest not in lease.receipts:
        raise Rejected('HISTORY_FORBIDDEN')
    # Unverified metadata may only narrow access, never authorize disclosure.
    # Check rights first so inaccessible/corrupt/missing objects share a refusal.
    try:
        actor = lease.actor
        core._permit(actor, 'product:' + lease.product, 'history')
        row = core.db.execute("SELECT body FROM objects WHERE tenant=? AND digest=? AND kind='document-receipt'",
                              (actor.tenant, receipt_digest)).fetchone()
        meta = decode(row[0]) if row else {}
        if meta['productId'] != lease.product or meta['manifestDigest'] != lease.manifest:
            raise ValueError()
        if meta['principal'] != actor.principal:
            core._permit(actor, 'receipt:' + receipt_digest, 'history')
        row = core.db.execute("SELECT body FROM objects WHERE tenant=? AND digest=? AND kind='source-revision'",
                              (actor.tenant, meta['sourceDigest'])).fetchone()
        source_meta = decode(row[0]) if row else {}
        core._permit(actor, 'source:' + source_meta['id'], 'source_read')
    except (Rejected, ValueError, KeyError, TypeError):
        raise Rejected('HISTORY_FORBIDDEN') from None
    try:
        replay = core.replay_document(actor, receipt_digest)
        return {k: v for k, v in replay.items() if k not in ('receiptDigest', 'replay')}
    except Rejected as exc:
        code = 'HISTORY_FORBIDDEN' if exc.code in ('FORBIDDEN', 'NOT_FOUND') else 'HISTORY_INTEGRITY_FAILED'
        raise Rejected(code) from None
    except (ValueError, TypeError, KeyError):
        raise Rejected('HISTORY_INTEGRITY_FAILED') from None


def project(core, actor, saved, receipt_digest):
    """Validate immutable evidence offline; never retrieve or regenerate it."""
    validate('savedReceipt', saved, 'HISTORY_INTEGRITY_FAILED')
    if digest(saved) != receipt_digest:
        raise Rejected('HISTORY_INTEGRITY_FAILED')
    manifest = core._get(actor, saved['manifestDigest'], 'document-manifest')
    source = core._get(actor, saved['sourceDigest'], 'source-revision')
    index = core._get(actor, saved['indexDigest'], 'document-index')
    binding = core._get(actor, saved['bindingDigest'], 'document-binding')
    core._get(actor, saved['policyDigest'], 'active-policy')
    candidate = core._get(actor, manifest['candidateDigest'], 'document-candidate')
    validation = core._get(actor, manifest['validationDigest'], 'document-validation')
    approval = core._get(actor, manifest['approvalDigest'], 'document-approval')
    checks = [manifest['productId'] == saved['productId'],
        manifest['sourceDigest'] == saved['sourceDigest'] == index['sourceDigest'],
        manifest['indexDigest'] == saved['indexDigest'] == candidate['indexDigest'],
        candidate['productId'] == saved['productId'] == binding['productId'],
        binding['manifestDigest'] == saved['manifestDigest'],
        validation['candidateDigest'] == approval['candidateDigest'] == manifest['candidateDigest'],
        approval['validationDigest'] == manifest['validationDigest'], validation['passed'] is True,
        sha256(index['originalHtml'].encode()).hexdigest() == index['originalDigest'],
        text_digest(source['content']) == source['contentDigest']]
    verify_bridge(index['originalHtml'].encode(), source, index['bridge'], index['bridgeDigest'])
    clauses = {c['clause']: c['text'] for c in index['clauses']}
    chunks = {c['id']: c for c in index['index']['chunks']}
    evidence = saved['result']['evidence']
    checks += [saved['result']['decision'] == ('EVIDENCE_FOUND' if evidence else 'EVIDENCE_NOT_FOUND'),
               len({e['clause'] for e in evidence}) == len(evidence)]
    for item in evidence:
        chunk = chunks[item['chunkId']]
        anchors = [m['anchor'] for m in index['bridge']['mappings'] if m['clause'] == item['clause']]
        checks += [item['clause'] in chunk['clauses'], text_digest(chunk['text']) == chunk['textDigest'],
            item['quote'] == clauses[item['clause']] == '\n'.join(a['quote'] for a in anchors),
            item['originalDigest'] == index['originalDigest'], item['anchors'] == anchors,
            set(item) == {'clause', 'quote', 'originalDigest', 'chunkId', 'anchors'}]
    if not all(checks):
        raise Rejected('HISTORY_INTEGRITY_FAILED')
    return {'code': 0, 'decision': 'EVIDENCE_FOUND' if evidence else 'UNKNOWN',
        'evidence': [{**e, 'sourceDigest': saved['sourceDigest']} for e in evidence],
        'receipt': {'schemaVersion': 'knowledge-receipt.v0.1', 'receiptId': 'kr-' + receipt_digest,
            'coreReceiptDigest': receipt_digest, 'productId': saved['productId'],
            'manifest': saved['manifestDigest'], 'businessDate': saved['host']['business_date'],
            'requestId': saved['requestId'], 'traceId': saved['traceId'],
            'sourceDigest': saved['sourceDigest'], 'sourceId': source['id'], 'sourceRevision': source['revision'],
            'indexDigest': saved['indexDigest'], 'bindingDigest': saved['bindingDigest'],
            'policyDigest': saved['policyDigest'], 'mode': saved['mode']}}


class HistoryRuntime:
    def __init__(self, database, authority, *, product, manifest):
        self.database = Path(database)
        self.resolve = HistoryLeases(authority)
        self.binding = product, manifest

    def lease(self, token):
        lease = self.resolve(token)
        if (lease.product, lease.manifest) != self.binding:
            raise Rejected('HISTORY_AUTH_REQUIRED')
        return lease

    def read(self, token, body):
        lease = self.lease(token)
        validate('request', body, 'HISTORY_REQUEST_INVALID')
        core = ReadOnlyDocumentCore(self.database)
        try:
            saved = authorized_replay(core, lease, body['coreReceiptDigest'])
            try:
                query = project(core, lease.actor, saved, body['coreReceiptDigest'])
            except (Rejected, KeyError, ValueError, TypeError):
                raise Rejected('HISTORY_INTEGRITY_FAILED') from None
            expected = {'productId': saved['productId'], 'manifest': saved['manifestDigest'],
                'sourceDigest': saved['sourceDigest'], 'sourceRevision': query['receipt']['sourceRevision'],
                'originalRequestId': saved['requestId'], 'originalTraceId': saved['traceId']}
            response = {'schemaVersion': 'knowledge-history.v0.1', 'code': 0, 'replay': True,
                'requestId': body['requestId'], 'traceId': body['traceId'],
                'coreReceiptDigest': body['coreReceiptDigest'], 'savedReceipt': saved, 'queryResponse': query}
            validate('response', response, 'HISTORY_INTEGRITY_FAILED')
            raw = json.dumps(response, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            if self.lease(token) != lease:
                raise Rejected('HISTORY_AUTH_REQUIRED')
            # A fresh read transaction sees revocation committed during validation.
            if authorized_replay(core, lease, body['coreReceiptDigest']) != saved:
                raise Rejected('HISTORY_INTEGRITY_FAILED')
            if body['expected'] != expected:
                raise Rejected('HISTORY_REFERENCE_MISMATCH')
            if len(raw) > MAX_RESPONSE:
                raise Rejected('HISTORY_RESPONSE_LIMIT')
            return raw
        finally:
            core.close()
