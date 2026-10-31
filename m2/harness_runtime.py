"""Consumption-only H1a adapter. No authority creation or publication operations.

The authenticated Host supplies a lease via a trusted resolver; JSON assertions
are compared to that lease, never converted into an Actor or BusinessContext.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
import json
import re

from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore
from knowledge_core.contracts import Rejected
from m2.runtime_protocol import validate_wire


@dataclass(frozen=True)
class Lease:
    actor: Actor
    context: BusinessContext
    subject: str
    session: str
    product: str
    manifest: str
    expires: datetime

    def check(self):
        if (self.actor.privileges or not self.actor.authority or not self.subject or not self.session
                or not re.fullmatch(r'[a-f0-9]{64}', self.manifest)
                or self.expires.tzinfo is None or self.expires <= datetime.now(timezone.utc)):
            raise Rejected('KNOWLEDGE_SESSION_REJECTED')
        self.context.facts()


class Runtime:
    def __init__(self, database, resolve_lease, client_factory, *, binding=None):
        self.database = database
        self.resolve_lease = resolve_lease
        self.client_factory = client_factory
        self.binding = None if binding is None else (binding['productId'], binding['manifest'])

    def lease(self, credential):
        if not isinstance(credential, str) or len(credential) < 32:
            raise Rejected('KNOWLEDGE_AUTH_REQUIRED')
        lease = self.resolve_lease(credential)
        if not isinstance(lease, Lease):
            raise Rejected('KNOWLEDGE_AUTH_REQUIRED')
        lease.check()
        if self.binding is not None and (lease.product, lease.manifest) != self.binding:
            raise Rejected('KNOWLEDGE_BINDING_MISMATCH')
        return lease

    def query(self, credential, body):
        lease = self.lease(credential)
        expected = {
            'schemaVersion': 'knowledge-query.v0.1',
            'capabilityId': 'knowledge.evidence.search',
            'productId': lease.product, 'manifest': lease.manifest,
            'businessDate': lease.context.business_date,
            'principalId': lease.actor.principal, 'subjectRef': lease.subject,
            'sessionRef': lease.session, 'purpose': lease.context.purpose,
        }
        if not isinstance(body, dict) or set(body) != set(expected) | {'arguments', 'requestId', 'traceId'}:
            raise Rejected('KNOWLEDGE_QUERY_INVALID')
        if any(body[key] != value for key, value in expected.items()):
            raise Rejected('KNOWLEDGE_CONTEXT_MISMATCH')
        validate_wire('queryRequest', body)
        arguments = body['arguments']
        if not isinstance(arguments, dict) or set(arguments) != {'question'}:
            raise Rejected('KNOWLEDGE_QUERY_INVALID')
        core = DocumentCore(self.database)
        client = None
        try:
            # Do not even initialize the upstream client before Core admission.
            core._query_binding(lease.actor, lease.product, lease.manifest, lease.context)
            client = self.client_factory()
            result = core.query_document(lease.actor, lease.product, lease.manifest, lease.context,
                arguments['question'], body['requestId'], body['traceId'], client)
            if self.lease(credential) != lease:
                raise Rejected('KNOWLEDGE_SESSION_CHANGED')
            # Session checks can block; check current Core permissions again before disclosure.
            core._query_binding(lease.actor, lease.product, lease.manifest, lease.context)
            source = core._get(lease.actor, result['sourceDigest'], 'source-revision')
            evidence = [{**item, 'sourceDigest': result['sourceDigest']} for item in result['result']['evidence']]
            response = {'code': 0, 'decision': 'EVIDENCE_FOUND' if evidence else 'UNKNOWN', 'evidence': evidence,
                'receipt': {'schemaVersion': 'knowledge-receipt.v0.1',
                    'receiptId': 'kr-' + result['receiptDigest'], 'coreReceiptDigest': result['receiptDigest'],
                    'productId': lease.product, 'manifest': lease.manifest,
                    'businessDate': lease.context.business_date, 'requestId': result['requestId'],
                    'traceId': result['traceId'], 'sourceDigest': result['sourceDigest'],
                    'sourceId': source['id'], 'sourceRevision': source['revision'],
                    'indexDigest': result['indexDigest'], 'bindingDigest': result['bindingDigest'],
                    'policyDigest': result['policyDigest'], 'mode': 'M2_ISOLATED_DOCUMENT'}}
            validate_wire('queryResponse', response)
            return response
        finally:
            core.close()
            if client is not None and hasattr(client, 'close'):
                client.close()

    def session(self, credential, body):
        """Recheck current consumption authority without retrieving or granting."""
        if body != {}:
            raise Rejected('KNOWLEDGE_QUERY_INVALID')
        validate_wire('sessionRequest', body)
        lease = self.lease(credential)
        core = DocumentCore(self.database)
        try:
            core._query_binding(lease.actor, lease.product, lease.manifest, lease.context)
            if self.lease(credential) != lease:
                raise Rejected('KNOWLEDGE_SESSION_CHANGED')
            core._query_binding(lease.actor, lease.product, lease.manifest, lease.context)
            result = {'code': 0, 'schemaVersion': 'knowledge-session-check.v0.1',
                'sessionRef': lease.session, 'productId': lease.product, 'manifest': lease.manifest}
            validate_wire('sessionResponse', result)
            return result
        finally:
            core.close()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_KEY')
        result[key] = value
    return result


def handler(runtime):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No tokens, request bodies or URLs in generic server logs.

        def respond(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode()
            if len(raw) > 262144:
                status, raw = 503, b'{"code":503,"error":"KNOWLEDGE_RESPONSE_LIMIT"}'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.respond(404, {'code': 404, 'error': 'NOT_FOUND'})

        def do_POST(self):
            if self.path not in ('/query', '/session'):
                return self.respond(404, {'code': 404, 'error': 'NOT_FOUND'})
            try:
                if len(self.headers.get_all('Authorization', [])) != 1:
                    raise Rejected('KNOWLEDGE_AUTH_REQUIRED')
                auth = self.headers['Authorization']
                if not auth.startswith('Bearer '):
                    raise Rejected('KNOWLEDGE_AUTH_REQUIRED')
                runtime.lease(auth[7:])
                if (self.headers.get('Transfer-Encoding') is not None
                        or len(self.headers.get_all('Content-Length', [])) != 1
                        or self.headers.get_content_type() != 'application/json'):
                    raise ValueError('INVALID_BODY')
                size = int(self.headers['Content-Length'])
                if not 0 < size <= 16384:
                    raise ValueError('INVALID_BODY')
                self.connection.settimeout(5)
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError('INVALID_BODY')
                body = json.loads(raw, object_pairs_hook=_unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError('INVALID_NUMBER')))
                operation = runtime.query if self.path == '/query' else runtime.session
                self.respond(200, operation(auth[7:], body))
            except Rejected as exc:
                self.respond(403, {'code': 403, 'error': exc.code})
            except (ValueError, TypeError, UnicodeError):
                self.respond(400, {'code': 400, 'error': 'KNOWLEDGE_QUERY_INVALID'})
            except Exception:
                self.respond(503, {'code': 503, 'error': 'KNOWLEDGE_UNAVAILABLE'})
    return Handler
