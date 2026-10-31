"""Real loopback HTTP with synthetic Host files and isolated Core databases."""
import copy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import http.client
import json
from pathlib import Path
import sqlite3
import threading

import pytest

from knowledge_core.contracts import Rejected, canonical, digest
from m2.history_runtime import HistoryRuntime, ReadOnlyDocumentCore, MAX_RESPONSE
from m2.history_service import HistoryServer, handler
from tests.test_m2_documents import prepared, released, query, AUTHOR, READER
from tests.support import policy

TOKEN = 'history-fixture-only-' + 'h' * 40


def private_json(path, body):
    path.write_text(json.dumps(body))
    path.chmod(0o600)


def host_files(directory, receipt, *, principal=READER.principal, tenant=READER.tenant):
    """Test issuer only, never imported by the history service."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    leases = directory / 'history-leases'
    leases.mkdir(mode=0o700, exist_ok=True)
    now = datetime.now(timezone.utc)
    authority = {'schemaVersion': 'knowledge-history-authority.v0.1', 'enabled': True,
        'ownerRef': 'synthetic-test-owner', 'principalId': principal, 'tenant': tenant,
        'authority': 'synthetic-test-history-host', 'purpose': 'knowledge.history.read',
        'productId': receipt['productId'], 'manifest': receipt['manifestDigest'],
        'allowedReceiptDigests': [receipt['receiptDigest']], 'expiresAt': (now + timedelta(minutes=10)).isoformat(),
        'leaseDirectory': str(leases)}
    path = directory / 'history-authority.json'
    private_json(path, authority)
    lease = {'schemaVersion': 'knowledge-history-lease.v0.1',
        'policyDigest': sha256(path.read_bytes()).hexdigest(), 'ownerRef': authority['ownerRef'],
        'viewerSessionRef': 'new-stopped-instance-view', 'expiresAt': (now + timedelta(minutes=5)).isoformat()}
    lease_path = leases / (sha256(TOKEN.encode()).hexdigest() + '.json')
    private_json(lease_path, lease)
    return path, lease_path


def history_request(receipt, source):
    return {'schemaVersion': 'knowledge-history.v0.1', 'requestId': 'history-1', 'traceId': 'history-trace-1',
        'coreReceiptDigest': receipt['receiptDigest'], 'expected': {
            'productId': receipt['productId'], 'manifest': receipt['manifestDigest'],
            'sourceDigest': receipt['sourceDigest'], 'sourceRevision': source['revision'],
            'originalRequestId': receipt['requestId'], 'originalTraceId': receipt['traceId']}}


@pytest.fixture
def history(prepared, tmp_path):
    core, client, _, db = prepared
    manifest, _, _ = released(prepared)
    saved = query(prepared, manifest)
    authority, lease = host_files(tmp_path / 'host', saved)
    runtime = HistoryRuntime(db, authority, product=saved['productId'], manifest=manifest)
    body = history_request(saved, core._get(AUTHOR, saved['sourceDigest'], 'source-revision'))
    server = HistoryServer(('127.0.0.1', 0), handler(runtime))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    def post(value=None, token=TOKEN, raw=None, path='/history/read', extra=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        headers.update(extra or {})
        payload = json.dumps(body if value is None else value).encode() if raw is None else raw
        try:
            connection.request('POST', path, payload, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()
    before_calls = client.calls
    before_receipts = core.db.execute("SELECT digest,body FROM objects WHERE kind='document-receipt' ORDER BY digest").fetchall()
    yield runtime, body, saved, authority, lease, post, core, client
    server.shutdown()
    server.server_close()
    thread.join()
    assert client.calls == before_calls
    assert core.db.execute("SELECT digest,body FROM objects WHERE kind='document-receipt' ORDER BY digest").fetchall() == before_receipts


def refresh_authority(authority, lease, **updates):
    value = json.loads(authority.read_bytes())
    value.update(updates)
    private_json(authority, value)
    view = json.loads(lease.read_bytes())
    view['policyDigest'] = sha256(authority.read_bytes()).hexdigest()
    private_json(lease, view)


def test_stopped_new_history_authority_exact_replay_no_execution(history, monkeypatch):
    runtime, body, saved, _, _, post, core, client = history
    def forbidden(*_):
        pytest.fail('History must not retrieve, execute or create receipts')
    from knowledge_core.documents import DocumentCore
    monkeypatch.setattr(DocumentCore, '_retrieve', forbidden)
    monkeypatch.setattr(DocumentCore, '_put', forbidden)
    client.error = 'RAGFLOW_UNAVAILABLE'
    status, response = post()
    assert status == 200
    assert response['savedReceipt'] == {k: v for k, v in saved.items() if k != 'receiptDigest'}
    assert digest(response['savedReceipt']) == body['coreReceiptDigest']
    assert response['queryResponse']['receipt']['requestId'] == saved['requestId']
    assert response['requestId'] == body['requestId'] != saved['requestId']
    assert post()[1] == response
    reopened = HistoryRuntime(runtime.database, runtime.resolve.authority, product=runtime.binding[0], manifest=runtime.binding[1])
    assert json.loads(reopened.read(TOKEN, body)) == response


@pytest.mark.parametrize('field', ['productId', 'manifest', 'sourceDigest', 'sourceRevision', 'originalRequestId', 'originalTraceId'])
def test_all_original_references_match(history, field):
    _, body, _, _, _, post, _, _ = history
    bad = copy.deepcopy(body)
    bad['expected'][field] = 99 if field == 'sourceRevision' else ('0'*64 if field in ('manifest', 'sourceDigest') else 'different')
    assert post(bad) == (409, {'code': 409, 'error': 'HISTORY_REFERENCE_MISMATCH'})


@pytest.mark.parametrize('case', ['missing', 'expired', 'forged', 'run-lease', 'run-authority', 'disabled',
    'policy-expired', 'too-long', 'wrong-owner', 'unknown-token', 'lease-mode', 'policy-mode', 'lease-symlink', 'wrong-binding'])
def test_history_credentials_fail_closed(history, case):
    _, _, _, authority, lease, post, _, _ = history
    item = json.loads(lease.read_bytes())
    if case == 'missing': lease.unlink()
    elif case == 'expired':
        item['expiresAt'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        private_json(lease, item)
    elif case == 'forged':
        item['policyDigest'] = '0'*64
        private_json(lease, item)
    elif case == 'run-lease':
        item['schemaVersion'] = 'knowledge-host-lease.v0.1'
        private_json(lease, item)
    elif case == 'run-authority': refresh_authority(authority, lease, schemaVersion='knowledge-host-authority.v0.1')
    elif case == 'disabled': refresh_authority(authority, lease, enabled=False)
    elif case == 'policy-expired': refresh_authority(authority, lease, expiresAt='2000-01-01T00:00:00Z')
    elif case == 'too-long':
        refresh_authority(authority, lease, expiresAt=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat())
        item = json.loads(lease.read_bytes())
        item['expiresAt'] = (datetime.now(timezone.utc)+timedelta(minutes=16)).isoformat()
        private_json(lease, item)
    elif case == 'wrong-owner':
        item['ownerRef'] = 'other'
        private_json(lease, item)
    elif case == 'lease-mode': lease.chmod(0o644)
    elif case == 'policy-mode': authority.chmod(0o644)
    elif case == 'lease-symlink':
        target = lease.with_suffix('.target')
        lease.rename(target)
        lease.symlink_to(target)
    elif case == 'wrong-binding': refresh_authority(authority, lease, manifest='0'*64)
    assert post(token='other-valid-length-'+'q'*40 if case == 'unknown-token' else TOKEN) == (
        403, {'code': 403, 'error': 'HISTORY_AUTH_REQUIRED'})


@pytest.mark.parametrize('kind', ['source', 'history', 'host-allowlist', 'tenant'])
def test_current_permission_denied(history, kind):
    _, _, _, authority, lease, post, core, _ = history
    if kind == 'host-allowlist': refresh_authority(authority, lease, allowedReceiptDigests=['0'*64])
    elif kind == 'tenant': refresh_authority(authority, lease, tenant='other')
    else: core.set_policy(AUTHOR, policy(2, source_reader=kind != 'source', history=kind != 'history'), 1)
    assert post() == (403, {'code': 403, 'error': 'HISTORY_FORBIDDEN'})


def test_cross_principal_requires_both_exact_grants(history):
    _, _, saved, authority, lease, post, core, _ = history
    refresh_authority(authority, lease, principalId='delegate')
    current = policy(2)
    current['grants'] += [{'principal': 'delegate', 'resource': g['resource'], 'actions': g['actions']}
                          for g in current['grants'] if g['principal'] == READER.principal]
    core.set_policy(AUTHOR, current, 1)
    assert post()[0] == 403
    current['revision'] = 3
    current['grants'].append({'principal': 'delegate', 'resource': 'receipt:'+saved['receiptDigest'], 'actions': ['history']})
    core.set_policy(AUTHOR, current, 2)
    assert post()[0] == 200
    refresh_authority(authority, lease, allowedReceiptDigests=['0'*64])
    assert post()[0] == 403


def test_historic_binding_and_source_need_not_be_current(history):
    _, _, saved, _, _, post, core, _ = history
    manifest = core._get(AUTHOR, saved['manifestDigest'], 'document-manifest')
    manifest['revision'] = 2
    with core.tx():
        new = core._put(AUTHOR, 'document-manifest', manifest)
    core.bind_document(AUTHOR, new, 1)
    core.activate_source(AUTHOR, saved['sourceDigest'], '2027-01-01', state='REVOKED')
    assert post()[0] == 200


@pytest.mark.parametrize('kind', ['source', 'history', 'host', 'lease'])
def test_return_time_revocation(history, monkeypatch, kind):
    _, _, _, authority, lease, post, core, _ = history
    import m2.history_runtime as module
    original = module.project
    def revoke(*args):
        result = original(*args)
        # Open the test writer on the HTTP worker thread.
        from knowledge_core.documents import DocumentCore
        writer = DocumentCore(history[0].database)
        try:
            if kind in ('source', 'history'):
                writer.set_policy(AUTHOR, policy(2, source_reader=kind != 'source', history=kind != 'history'), 1)
            elif kind == 'host': refresh_authority(authority, lease, enabled=False)
            else: lease.unlink()
        finally: writer.close()
        return result
    monkeypatch.setattr(module, 'project', revoke)
    assert post()[0] == 403


@pytest.mark.parametrize('raw', [b'{"requestId":1,"requestId":2}', b'{"value":NaN}', b'[]', b'x'*16385])
def test_invalid_requests(history, raw):
    assert history[5](raw=raw) == (400, {'code': 400, 'error': 'HISTORY_REQUEST_INVALID'})


def test_missing_receipt_not_an_existence_oracle(history):
    _, body, _, authority, lease, post, _, _ = history
    refresh_authority(authority, lease, allowedReceiptDigests=['0'*64])
    assert post({**body, 'coreReceiptDigest': '0'*64}) == (403, {'code': 403, 'error': 'HISTORY_FORBIDDEN'})


def test_no_publishing_or_runtime_routes(history):
    for path in ('/query', '/session', '/publish', '/grant'):
        assert history[5](path=path)[0] == 400


def test_read_only_database_enforced(history):
    core = ReadOnlyDocumentCore(history[0].database)
    try:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            core.db.execute('DELETE FROM heads')
    finally: core.close()


def test_response_limit_refuses_full_body_not_truncates(history, monkeypatch):
    # Transport defence test; not a claim that the real saved receipt is oversized.
    runtime, _, _, _, _, post, _, _ = history
    monkeypatch.setattr(runtime, 'read', lambda *_: b'x'*(MAX_RESPONSE+1))
    assert post() == (413, {'code': 413, 'error': 'HISTORY_RESPONSE_LIMIT'})


def test_authorized_chain_corruption(history):
    _, _, saved, _, _, post, core, _ = history
    core.db.execute('DROP TRIGGER immutable_object_update')
    core.db.execute("UPDATE objects SET body='{}' WHERE digest=?", (saved['indexDigest'],))
    assert post() == (409, {'code': 409, 'error': 'HISTORY_INTEGRITY_FAILED'})


def test_storage_outage_then_recovery(history):
    runtime, _, _, _, _, post, _, _ = history
    original = runtime.database
    runtime.database = original.parent / 'missing.db'
    assert post() == (503, {'code': 503, 'error': 'HISTORY_UNAVAILABLE'})
    assert not runtime.database.exists()
    runtime.database = original
    assert post()[0] == 200


def test_actual_serialized_response_limit(prepared, tmp_path):
    core, _, _, db = prepared
    manifest, _, _ = released(prepared)
    saved = query(prepared, manifest)
    saved.pop('receiptDigest')
    saved['result']['syntheticOversizeDiagnostic'] = 'x' * MAX_RESPONSE
    with core.tx():
        sha = core._put(AUTHOR, 'document-receipt', saved)
    saved['receiptDigest'] = sha
    authority, _ = host_files(tmp_path / 'host', saved)
    runtime = HistoryRuntime(db, authority, product=saved['productId'], manifest=manifest)
    body = history_request(saved, core._get(AUTHOR, saved['sourceDigest'], 'source-revision'))
    before = core.db.execute("SELECT count(*) FROM objects WHERE kind='document-receipt'").fetchone()
    with pytest.raises(Rejected, match='HISTORY_RESPONSE_LIMIT'):
        runtime.read(TOKEN, body)
    assert core.db.execute("SELECT count(*) FROM objects WHERE kind='document-receipt'").fetchone() == before


@pytest.mark.parametrize('target', ['receipt', 'anchors', 'source-version'])
def test_invalid_saved_receipt_or_evidence_on_copy(history, tmp_path, target):
    runtime, body, saved, authority, lease, post, core, _ = history
    copied = sqlite3.connect(tmp_path / 'corrupt.sqlite', isolation_level=None)
    core.db.backup(copied)
    runtime.database = tmp_path / 'corrupt.sqlite'
    copied.execute('DROP TRIGGER immutable_object_update')
    if target == 'receipt':
        copied.execute("UPDATE objects SET body='{}' WHERE digest=?", (saved['receiptDigest'],))
        expected = 403  # Unable to authorize metadata: no existence oracle.
    else:
        original = core._get(READER, saved['receiptDigest'], 'document-receipt')
        if target == 'anchors': original['result']['evidence'][0]['anchors'][0]['quote'] = 'invented'
        else: original['sourceDigest'] = saved['indexDigest']
        sha = digest(original)
        copied.execute('INSERT INTO objects VALUES(?,?,?,?)', (READER.tenant, sha, 'document-receipt', canonical(original)))
        body['coreReceiptDigest'] = sha
        refresh_authority(authority, lease, allowedReceiptDigests=[sha])
        expected = 409 if target == 'anchors' else 403
    copied.close()
    assert post()[0] == expected
