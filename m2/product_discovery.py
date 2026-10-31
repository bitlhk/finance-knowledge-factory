"""Host-authorized metadata discovery. No upstream retrieval or authority issuer."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from knowledge_core.contracts import Rejected
from knowledge_core.core import Actor, BusinessContext
from m2.history_runtime import ReadOnlyDocumentCore, private_read, decode
from m2.product_release import describe, validate

MAX_RESPONSE = 512 * 1024
ERRORS = {'DISCOVERY_REQUEST_INVALID': 400, 'DISCOVERY_AUTH_REQUIRED': 403,
          'DISCOVERY_INTEGRITY_FAILED': 409, 'DISCOVERY_RESPONSE_LIMIT': 413,
          'DISCOVERY_UNAVAILABLE': 503}


@dataclass(frozen=True)
class DiscoveryLease:
    actor: Actor
    context: BusinessContext
    products: tuple
    session: str
    expires: datetime
    policy_digest: str
    lease_digest: str


class DiscoveryLeases:
    """Read Host files only; a discovery token is never a consumption grant."""
    def __init__(self, authority):
        self.authority = Path(authority)

    def __call__(self, token):
        try:
            if not isinstance(token, str) or not 32 <= len(token) <= 4096:
                raise ValueError()
            raw = private_read(self.authority)
            policy = decode(raw)
            validate('hostAuthority', policy, 'DISCOVERY_AUTH_REQUIRED')
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
            validate('hostLease', lease, 'DISCOVERY_AUTH_REQUIRED')
            end = datetime.fromisoformat(lease['expiresAt'].replace('Z', '+00:00'))
            if (lease['ownerRef'] != policy['ownerRef'] or lease['policyDigest'] != sha256(raw).hexdigest()
                    or not now < end <= expiry or (end - now).total_seconds() > 900):
                raise ValueError()
            actor = Actor(policy['tenant'], policy['principalId'], policy['authority'])
            context = BusinessContext(**policy['context'])
            context.facts()
            return DiscoveryLease(actor, context, tuple(policy['allowedProductIds']),
                lease['builderSessionRef'], end, sha256(raw).hexdigest(), sha256(lease_raw).hexdigest())
        except (OSError, ValueError, TypeError, KeyError, Rejected):
            raise Rejected('DISCOVERY_AUTH_REQUIRED') from None


class DiscoveryRuntime:
    def __init__(self, database, resolve_lease, connection_ref):
        if isinstance(connection_ref, str):
            connection_ref = {'*': connection_ref}
        if (not isinstance(connection_ref, dict) or not connection_ref
                or any(not isinstance(product, str) or not product for product in connection_ref)
                or any(not isinstance(ref, str) or not re.fullmatch('[a-z][a-z0-9-]{0,63}', ref)
                       for ref in connection_ref.values())):
            raise ValueError('INVALID_CONNECTION_REF')
        self.database, self.resolve_lease = database, resolve_lease
        self.connection_refs = dict(connection_ref)

    def connection_ref(self, product):
        ref = self.connection_refs.get(product, self.connection_refs.get('*'))
        if ref is None:
            raise Rejected('DISCOVERY_INTEGRITY_FAILED')
        return ref

    def lease(self, credential):
        lease = self.resolve_lease(credential)
        if (not isinstance(lease, DiscoveryLease) or lease.actor.privileges or not lease.actor.authority
                or lease.expires <= datetime.now(timezone.utc)):
            raise Rejected('DISCOVERY_AUTH_REQUIRED')
        return lease

    def collect(self, lease):
        core = ReadOnlyDocumentCore(self.database)
        try:
            with core.tx():
                products = []
                for product in sorted(set(lease.products)):
                    try:
                        core._permit(lease.actor, 'product:' + product, 'consume')
                    except Rejected:
                        continue
                    _, binding_sha = core._head(lease.actor, 'document-binding', product)
                    if binding_sha is None:
                        continue
                    try:
                        binding = core._get(lease.actor, binding_sha, 'document-binding')
                        products.append(describe(core, lease.actor, lease.context, product,
                            binding['manifestDigest'], self.connection_ref(product)))
                    except Rejected as exc:
                        if exc.code in ('FORBIDDEN', 'SOURCE_NOT_EFFECTIVE',
                                        'SOURCE_SUPERSEDED_OR_REVOKED', 'KNOWLEDGE_NOT_APPLICABLE'):
                            continue
                        raise Rejected('DISCOVERY_INTEGRITY_FAILED') from None
                return products
        finally:
            core.close()

    def discover(self, credential, body):
        lease = self.lease(credential)
        validate('request', body, 'DISCOVERY_REQUEST_INVALID')
        products = self.collect(lease)
        if self.lease(credential) != lease:
            raise Rejected('DISCOVERY_AUTH_REQUIRED')
        # A second read sees policy/binding changes committed during Host rechecking.
        if self.collect(lease) != products:
            raise Rejected('DISCOVERY_AUTH_REQUIRED')
        now = datetime.now(timezone.utc)
        if lease.expires <= now:
            raise Rejected('DISCOVERY_AUTH_REQUIRED')
        response = {'schemaVersion': 'knowledge-products-discover.v0.1', 'code': 0,
            'requestId': body['requestId'], 'traceId': body['traceId'], 'checkedAt': now.isoformat(),
            'expiresAt': min(now + timedelta(seconds=60), lease.expires).isoformat(), 'products': products}
        validate('response', response)
        raw = json.dumps(response, ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > MAX_RESPONSE:
            raise Rejected('DISCOVERY_RESPONSE_LIMIT')
        return raw
