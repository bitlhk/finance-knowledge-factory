"""Discovery and generic service tests; controlled retrieval is explicitly not RAGFlow."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib import request, error

import pytest

from knowledge_core.contracts import Rejected, digest
from m2.discovery_service import DiscoveryServer, handler
from m2.product_discovery import DiscoveryLeases, DiscoveryRuntime
from m2.product_release import read_release, validate, SCHEMA_SHA256
from m2.synthetic_context import AUTHOR, READER, CONTEXT
from tests.runtime_support import make

TOKEN = 'synthetic-discovery-only-token-not-a-real-secret'
BODY = {'schemaVersion': 'knowledge-products-discover.v0.1', 'requestId': 'discover-1', 'traceId': 'trace-1'}


def write_private(path, body):
    path.write_text(json.dumps(body))
    path.chmod(0o600)


@pytest.fixture
def setup(tmp_path):
    service, client, product, release = make(tmp_path)
    directory = tmp_path / 'leases'
    directory.mkdir(mode=0o700)
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    authority = tmp_path / 'authority.json'
    policy = {'schemaVersion': 'knowledge-discovery-authority.v0.1', 'enabled': True,
        'ownerRef': 'builder-test', 'tenant': READER.tenant, 'principalId': READER.principal,
        'authority': READER.authority, 'allowedProductIds': [product['id']],
        'context': asdict(CONTEXT), 'expiresAt': expiry, 'leaseDirectory': str(directory)}
    write_private(authority, policy)
    lease_path = directory / (sha256(TOKEN.encode()).hexdigest() + '.json')
    lease = {'schemaVersion': 'knowledge-discovery-lease.v0.1', 'ownerRef': policy['ownerRef'],
        'policyDigest': sha256(authority.read_bytes()).hexdigest(), 'builderSessionRef': 'builder-1', 'expiresAt': expiry}
    write_private(lease_path, lease)
    runtime = DiscoveryRuntime(service.database, DiscoveryLeases(authority), 'knowledge-factory-isolated')
    return service, client, product, release, runtime, authority, lease_path


def discover(setup):
    return json.loads(setup[4].discover(TOKEN, BODY))


def test_real_descriptor_sample_contract_and_frozen_digests():
    root = Path(__file__).resolve().parents[1]
    sample = json.loads((root / 'examples/products/h1a-release.json').read_text())
    validate('release', sample['descriptor'])
    assert digest(sample['descriptor']) == sample['descriptorDigest']
    assert SCHEMA_SHA256 == '0b671ae3de0dcb04e0614a9bed80ee38b7cd4672fb9db9df064aabe25f0a7e4e'
    assert sample['descriptor']['protocols']['query']['schemaDigest'] == sha256(
        (root / 'contracts/runtime/knowledge-runtime-v0.1.schema.json').read_bytes()).hexdigest()
    assert sample['descriptor']['protocols']['history']['schemaDigest'] == sha256(
        (root / 'contracts/runtime/knowledge-history-v0.1.proposed.schema.json').read_bytes()).hexdigest()


def test_generic_product_read_only_no_retrieval_or_new_receipt(setup):
    service, client, product, release, *_ = setup
    before, calls = service.database.read_bytes(), client.calls
    response = discover(setup)
    item = response['products'][0]
    assert item['descriptor']['productId'] == product['id'] != 'run-39d069d400924257a857cfa7ec64917b'
    assert item['descriptor']['manifestDigest'] == release['manifestDigest']
    assert item['descriptor']['publication']['productionAuthorized'] is False
    assert item['descriptorDigest'] == digest(item['descriptor'])
    assert 'originalHtml' not in json.dumps(response) and 'datasetId' not in json.dumps(response)
    assert 0 < (datetime.fromisoformat(response['expiresAt']) - datetime.fromisoformat(response['checkedAt'])).total_seconds() <= 60
    assert service.database.read_bytes() == before and client.calls == calls


def test_product_specific_connection_is_projected(setup):
    service, _, product, _, _, authority, _ = setup
    runtime = DiscoveryRuntime(service.database, DiscoveryLeases(authority),
        {product['id']: 'knowledge-product-specific'})
    item = json.loads(runtime.discover(TOKEN, BODY))['products'][0]
    assert item['descriptor']['connectionRef'] == 'knowledge-product-specific'


def test_missing_product_connection_fails_closed(setup):
    service, _, _, _, _, authority, _ = setup
    runtime = DiscoveryRuntime(service.database, DiscoveryLeases(authority),
        {'another-product': 'knowledge-other'})
    with pytest.raises(Rejected, match='DISCOVERY_INTEGRITY_FAILED'):
        json.loads(runtime.discover(TOKEN, BODY))


@pytest.mark.parametrize('case', ['missing', 'wrong-token', 'expired', 'wrong-owner', 'forged-policy', 'runtime-token', 'permissions', 'symlink'])
def test_discovery_host_authority_denials(setup, case):
    *_, runtime, authority, lease_path = setup
    if case == 'missing': lease_path.unlink()
    elif case == 'wrong-token':
        with pytest.raises(Rejected, match='DISCOVERY_AUTH_REQUIRED'): runtime.discover('wrong' * 10, BODY)
        return
    elif case == 'permissions': authority.chmod(0o644)
    elif case == 'symlink':
        actual = authority.with_suffix('.real')
        authority.rename(actual)
        authority.symlink_to(actual)
    else:
        lease = json.loads(lease_path.read_text())
        if case == 'expired': lease['expiresAt'] = '2000-01-01T00:00:00Z'
        if case == 'wrong-owner': lease['ownerRef'] = 'another-owner'
        if case == 'forged-policy': lease['policyDigest'] = '0' * 64
        if case == 'runtime-token': lease['schemaVersion'] = 'knowledge-host-lease.v0.1'
        write_private(lease_path, lease)
    with pytest.raises(Rejected, match='DISCOVERY_AUTH_REQUIRED'): discover(setup)


@pytest.mark.parametrize('case', ['source-revoked', 'consume-revoked', 'source-inactive', 'wrong-context', 'wrong-tenant', 'not-listed', 'unbound'])
def test_products_not_disclosed_without_current_authorization(setup, case):
    service, _, product, release, runtime, _, _ = setup
    if case in ('source-revoked', 'consume-revoked'):
        core = service.core()
        try:
            revision, sha = core._head(AUTHOR, 'policy', 'current')
            policy = core._get(AUTHOR, sha, 'active-policy')
            policy['revision'] = revision + 1
            action = 'source_read' if case == 'source-revoked' else 'consume'
            policy['grants'] = [g for g in policy['grants'] if not (g['principal'] == READER.principal and action in g['actions'])]
            core.set_policy(AUTHOR, policy, revision)
        finally: core.close()
    elif case == 'source-inactive':
        core = service.core()
        try:
            source = core._get(AUTHOR, release['manifestDigest'], 'document-manifest')['sourceDigest']
            core.activate_source(AUTHOR, source, '2026-02-01', 'REVOKED')
        finally: core.close()
    else:
        lease = runtime.lease(TOKEN)
        if case == 'wrong-context': lease = replace(lease, context=replace(lease.context, region='other'))
        if case == 'wrong-tenant': lease = replace(lease, actor=replace(lease.actor, tenant='other'))
        if case in ('not-listed', 'unbound'): lease = replace(lease, products=() if case == 'not-listed' else ('unbound',))
        runtime.resolve_lease = lambda _: lease
    assert discover(setup)['products'] == []


def test_draft_change_does_not_change_description(setup):
    before = discover(setup)['products']
    core = setup[0].core()
    try:
        revision, sha = core._head(AUTHOR, 'recipe', setup[2]['id'] + '-recipe')
        recipe = core._get(AUTHOR, sha, 'recipe')
        recipe.update(revision=revision + 1, intendedConsumers=['outsider'])
        core.save_recipe(AUTHOR, recipe, revision)
    finally: core.close()
    assert discover(setup)['products'] == before


def test_current_manifest_change_requires_new_selection(setup):
    service, _, product, release, *_ = setup
    core = service.core()
    try:
        old = core._get(AUTHOR, release['manifestDigest'], 'document-manifest')
        new = core.publish_document(AUTHOR, old['candidateDigest'], old['validationDigest'], old['approvalDigest'], 2)
        core.bind_document(AUTHOR, new, 1)
        with pytest.raises(Rejected, match='MANIFEST_MISMATCH'):
            read_release(service.database, READER, CONTEXT, product['id'], release['manifestDigest'], 'knowledge-factory-isolated')
    finally: core.close()
    assert discover(setup)['products'][0]['descriptor']['version'] == 2


def test_revoked_during_final_host_check_refuses_disclosure(setup):
    runtime = setup[4]
    original = runtime.resolve_lease
    calls = 0
    def resolve(token):
        nonlocal calls
        calls += 1
        if calls == 2:
            core = setup[0].core()
            try:
                _, sha = core._head(AUTHOR, 'policy', 'current')
                policy = core._get(AUTHOR, sha, 'active-policy')
                policy.update(revision=2, grants=[])
                core.set_policy(AUTHOR, policy, 1)
            finally: core.close()
        return original(token)
    runtime.resolve_lease = resolve
    with pytest.raises(Rejected, match='DISCOVERY_AUTH_REQUIRED'): discover(setup)


@pytest.mark.parametrize('extra', ['principalId', 'businessDate', 'url', 'productId'])
def test_client_cannot_supply_authority_or_endpoint(setup, extra):
    with pytest.raises(Rejected, match='DISCOVERY_REQUEST_INVALID'):
        setup[4].discover(TOKEN, {**BODY, extra: 'untrusted'})


def test_response_limit_is_not_truncated_success(setup, monkeypatch):
    monkeypatch.setattr('m2.product_discovery.MAX_RESPONSE', 100)
    with pytest.raises(Rejected, match='DISCOVERY_RESPONSE_LIMIT'): discover(setup)


def http(base, token=TOKEN, body=BODY, path='/products/discover'):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = request.Request(base + path, raw, headers)
    try: response = request.urlopen(req, timeout=5)
    except error.HTTPError as exc: response = exc
    with response:
        assert response.headers['Cache-Control'] == 'no-store'
        return response.status, json.loads(response.read())


def test_real_http_discovery_and_errors(setup):
    server = DiscoveryServer(('127.0.0.1', 0), handler(setup[4]))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        assert http(base)[0] == 200
        assert http(base, token=None)[0] == 403
        assert http(base, token='bad')[0] == 403
        assert http(base, body=b'{"requestId":"one","requestId":"two"}')[0] == 400
        assert http(base, body=b' ' * 16385)[0] == 400
        assert http(base, path='/query')[0] == 400
        setup[6].unlink()
        assert http(base)[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('mode', ['query', 'history'])
def test_generic_cli_accepts_non_h1a_binding_but_not_anonymous_consumption(setup, tmp_path, mode):
    service, _, product, release, *_ = setup
    binding = tmp_path / 'binding.json'
    binding.write_text(json.dumps({'schemaVersion': 'knowledge-runtime-binding.v0.1',
        'productId': product['id'], 'manifest': release['manifestDigest'], 'productionBaseline': 'test-only'}))
    ready = tmp_path / ('ready-' + mode + '.json')
    cmd = [sys.executable, '-m', 'm2.product_service', '--mode', mode, '--database', str(service.database),
        '--authority', str(tmp_path / 'missing-authority.json'), '--binding', str(binding),
        '--port', '0', '--ready-file', str(ready)]
    if mode == 'query': cmd += ['--private-config', str(tmp_path / 'absent-config')]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if ready.exists() or process.poll() is not None: break
            time.sleep(.05)
        assert ready.exists()
        meta = json.loads(ready.read_text())
        assert meta['binding']['productId'] == product['id']
        status, body = http('http://127.0.0.1:' + str(meta['port']), token=None, body={},
            path='/session' if mode == 'query' else '/history/read')
        assert status == 403
    finally:
        process.terminate()
        process.communicate(timeout=10)
    assert process.returncode == 0
    stopped = json.loads(ready.with_suffix('.stopped.json').read_text())
    if mode == 'history': assert stopped['outboundAttempts'] == 0
