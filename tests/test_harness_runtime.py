from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import threading
from http.server import ThreadingHTTPServer
from urllib import request, error

import pytest

from knowledge_core.contracts import Rejected
from m2.harness_runtime import Lease, Runtime, handler
from m2.acceptance import AUTHOR, READER, CONTEXT
from tests.test_m2_web import make, release
from tests.test_m2_documents import CASES
from tests.test_web_production import done

TOKEN = 'isolated-test-session-' + 'x' * 40


@pytest.fixture
def ready(tmp_path):
    service, client, data = make(tmp_path)
    job = done(service, service.submit(data))
    binding = release(service, job)
    lease = Lease(READER, CONTEXT, 'synthetic-subject', 'host-session', job['id'],
        binding['manifestDigest'], datetime.now(timezone.utc) + timedelta(minutes=5))
    current = {'lease': lease}
    runtime = Runtime(service.database, lambda credential: current['lease'] if credential == TOKEN else None, lambda: client)
    body = {'schemaVersion': 'knowledge-query.v0.1', 'capabilityId': 'knowledge.evidence.search',
        'productId': lease.product, 'manifest': lease.manifest, 'businessDate': CONTEXT.business_date,
        'principalId': READER.principal, 'subjectRef': lease.subject, 'sessionRef': lease.session,
        'purpose': CONTEXT.purpose, 'requestId': 'request-h1', 'traceId': 'trace-h1',
        'arguments': {'question': CASES[0]['question']}}
    yield runtime, body, current, service, client
    service.close()


def test_runtime_consumes_same_snapshot_and_does_not_publish_or_grant(ready):
    runtime, body, _, service, _ = ready
    core = service.core()
    heads = core.db.execute('SELECT * FROM heads ORDER BY tenant,kind,name').fetchall()
    activations = core.db.execute('SELECT * FROM activations').fetchall()
    result = runtime.query(TOKEN, body)
    assert result['code'] == 0 and result['decision'] == 'EVIDENCE_FOUND'
    receipt = result['receipt']
    assert receipt['manifest'] == body['manifest']
    assert receipt['requestId'] == body['requestId'] and receipt['traceId'] == body['traceId']
    saved = core.replay_document(READER, receipt['coreReceiptDigest'])
    assert saved['sourceDigest'] == receipt['sourceDigest']
    assert all(e['anchors'] and e['quote'] and e['sourceDigest'] == receipt['sourceDigest'] for e in result['evidence'])
    assert core.db.execute('SELECT * FROM heads ORDER BY tenant,kind,name').fetchall() == heads
    assert core.db.execute('SELECT * FROM activations').fetchall() == activations
    core.close()


@pytest.mark.parametrize('key,value', [('manifest', '0'*64), ('principalId', 'outsider'),
    ('subjectRef', 'someone-else'), ('businessDate', '2027-01-01'), ('sessionRef', 'other'),
    ('purpose', 'admin'), ('capabilityId', 'knowledge.rule.evaluate')])
def test_runtime_rejects_assertion_spoof_before_upstream(ready, key, value):
    runtime, body, _, _, client = ready
    before = client.calls
    with pytest.raises(Rejected, match='KNOWLEDGE_CONTEXT_MISMATCH'):
        runtime.query(TOKEN, {**body, key: value})
    assert client.calls == before


@pytest.mark.parametrize('kind', ['expired', 'missing-context', 'privileged', 'source-revoked', 'service-revoked'])
def test_runtime_requires_live_authority_and_core_permissions(ready, kind):
    runtime, body, current, service, client = ready
    lease = current['lease']
    if kind == 'expired':
        current['lease'] = replace(lease, expires=datetime.now(timezone.utc)-timedelta(seconds=1))
    elif kind == 'missing-context':
        current['lease'] = replace(lease, context=replace(CONTEXT, source=''))
    elif kind == 'privileged':
        current['lease'] = replace(lease, actor=AUTHOR)
    else:
        core = service.core()
        revision, sha = core._head(AUTHOR, 'policy', 'current')
        policy = core._get(AUTHOR, sha, 'active-policy')
        prefix = 'source:' if kind == 'source-revoked' else 'product:'
        policy['grants'] = [g for g in policy['grants'] if not (g['principal'] == READER.principal and g['resource'].startswith(prefix))]
        policy['revision'] = revision+1
        core.set_policy(AUTHOR, policy, revision)
        core.close()
    before = client.calls
    with pytest.raises(Rejected):
        runtime.query(TOKEN, body)
    assert client.calls == before


def test_runtime_rejects_late_session_revocation(ready):
    runtime, body, current, _, client = ready
    retrieve = client.retrieve
    def revoked(*args):
        result = retrieve(*args)
        current['lease'] = None
        return result
    client.retrieve = revoked
    with pytest.raises(Rejected, match='KNOWLEDGE_AUTH_REQUIRED'):
        runtime.query(TOKEN, body)


def test_current_session_rechecks_source_without_retrieval(ready):
    runtime, body, _, service, client = ready
    before = client.calls
    checked = runtime.session(TOKEN, {})
    assert checked['manifest'] == body['manifest']
    assert checked['sessionRef'] == body['sessionRef']
    assert client.calls == before
    core = service.core()
    revision, sha = core._head(AUTHOR, 'policy', 'current')
    policy = core._get(AUTHOR, sha, 'active-policy')
    policy['grants'] = [g for g in policy['grants'] if not (
        g['principal'] == READER.principal and g['resource'].startswith('source:'))]
    policy['revision'] = revision + 1
    core.set_policy(AUTHOR, policy, revision)
    core.close()
    with pytest.raises(Rejected):
        runtime.session(TOKEN, {})
    assert client.calls == before


def test_session_check_cannot_accept_browser_authority(ready):
    runtime, _, _, _, _ = ready
    with pytest.raises(Rejected):
        runtime.session(TOKEN, {'principalId': 'other'})
    with pytest.raises(Rejected):
        runtime.session('bad-token', {})


def test_runtime_upstream_business_error_never_becomes_success(ready):
    runtime, body, _, _, client = ready
    client.error = 'RAGFLOW_BUSINESS_ERROR'
    with pytest.raises(Rejected, match='RAGFLOW_BUSINESS_ERROR'):
        runtime.query(TOKEN, body)


def test_runtime_source_not_effective_is_not_activated_by_consumer(ready):
    runtime, body, current, _, client = ready
    current['lease'] = replace(current['lease'], context=replace(CONTEXT, business_date='2025-12-31'))
    before = client.calls
    with pytest.raises(Rejected, match='SOURCE_NOT_EFFECTIVE'):
        runtime.query(TOKEN, {**body, 'businessDate': '2025-12-31'})
    assert client.calls == before


def test_http_auth_strict_body_and_no_release_routes(ready):
    runtime, body, _, _, _ = ready
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(runtime))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def post(path='/query', token=TOKEN, raw=None):
        req = request.Request(f'http://127.0.0.1:{server.server_port}'+path,
            (json.dumps(body) if raw is None else raw).encode(),
            headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        try:
            with request.urlopen(req) as response: return response.status, json.load(response)
        except error.HTTPError as response: return response.code, json.load(response)
    try:
        assert post()[0] == 200
        assert post(token='wrong')[0] == 403
        assert post(path='/publish')[0] == 404
        assert post(path='/session', raw='{}')[0] == 200
        assert post(path='/session', raw='{}', token='wrong')[0] == 403
        assert post(raw='{"schemaVersion":1,"schemaVersion":2}')[0] == 400
        assert post(raw='{"arguments":NaN}')[0] == 400
        assert post(raw=json.dumps({**body, 'actor': 'admin'}))[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
