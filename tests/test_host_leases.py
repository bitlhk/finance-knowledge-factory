from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from m2.synthetic_context import READER, CONTEXT
from m2.host_leases import HostLeases


@pytest.fixture
def issued(tmp_path):
    directory = tmp_path / 'leases'
    directory.mkdir(mode=0o700)
    policy = tmp_path / 'authority.json'
    end = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    config = dict(schemaVersion='knowledge-host-authority.v0.1', enabled=True,
        ownerRef='isolated-owner', principalId=READER.principal, tenant=READER.tenant,
        authority=READER.authority, subjectRef='knowledge-subject', productId='product',
        manifest='a'*64, context=asdict(CONTEXT), expiresAt=end, leaseDirectory=str(directory))
    policy.write_text(json.dumps(config))
    policy.chmod(0o600)
    token = 'test-only-' + 'x'*48
    lease = directory / (sha256(token.encode()).hexdigest()+'.json')
    record = dict(schemaVersion='knowledge-host-lease.v0.1',
        policyDigest=sha256(policy.read_bytes()).hexdigest(), ownerRef=config['ownerRef'],
        instanceId='instance-1', sessionRef='session-1', expiresAt=end)
    lease.write_text(json.dumps(record))
    lease.chmod(0o600)
    return HostLeases(policy), token, policy, lease, config, record


def test_host_issued_lease_contains_no_authority_mutations_or_credential(issued):
    resolver, token, policy, lease, _, _ = issued
    found = resolver(token)
    assert found and found.actor == READER and found.context == CONTEXT
    assert found.actor.privileges == frozenset()
    assert found.session == 'session-1'
    assert token not in policy.read_text() + lease.read_text()
    assert resolver('wrong-token') is None
    lease.unlink()
    assert resolver(token) is None


@pytest.mark.parametrize('mutation', ['disabled', 'changed-policy', 'wrong-owner', 'expired',
    'extended', 'unsafe-policy', 'unsafe-lease', 'symlink', 'unsafe-directory', 'missing-context'])
def test_rejects_changed_or_untrusted_lease(issued, mutation):
    resolver, token, policy, lease, config, record = issued
    if mutation in ('disabled', 'changed-policy', 'missing-context'):
        if mutation == 'disabled': config['enabled'] = False
        elif mutation == 'missing-context': config['context'].pop('source')
        else: config['principalId'] = 'other'
        policy.write_text(json.dumps(config))
    elif mutation in ('wrong-owner', 'expired', 'extended'):
        if mutation == 'wrong-owner': record['ownerRef'] = 'other'
        elif mutation == 'expired': record['expiresAt'] = '2000-01-01T00:00:00Z'
        else: record['expiresAt'] = '2099-01-01T00:00:00Z'
        lease.write_text(json.dumps(record))
    elif mutation == 'unsafe-policy': policy.chmod(0o644)
    elif mutation == 'unsafe-lease': lease.chmod(0o644)
    elif mutation == 'unsafe-directory': lease.parent.chmod(0o755)
    else:
        target = lease.with_suffix('.saved')
        lease.rename(target)
        lease.symlink_to(target)
    assert resolver(token) is None
