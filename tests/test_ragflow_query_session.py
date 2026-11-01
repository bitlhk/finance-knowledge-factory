"""Concurrent HTTP tests with a rotating-login fixture, not native RAGFlow."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib import request

import pytest

from knowledge_core.contracts import Rejected
from m2.harness_runtime import handler
from m2.ragflow import Ragflow, RagflowQuerySession, NoRedirect
from m2.runtime_service import IsolatedServer
from m2.synthetic_context import AUTHOR, READER
from tests.runtime_support import http
from tests.test_harness_runtime import ready, TOKEN
from tests.test_runtime_http import listening


@contextmanager
def rotating_upstream(client):
    state = {'logins': 0, 'retrievals': 0, 'token': None, 'barrier': None,
             'login_failure': False, 'callback': None}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/auth/login':
                with lock:
                    state['logins'] += 1
                    state['token'] = 'synthetic-session-' + str(state['logins'])
                    token = state['token']
                self.send_response(503 if state['login_failure'] else 200)
                self.send_header('Authorization', token)
                raw = b'{"code":0,"data":{}}'
            else:
                with lock: state['retrievals'] += 1
                if state['barrier'] is not None: state['barrier'].wait(timeout=5)
                if state['callback'] is not None: state['callback']()
                accepted = self.headers.get('Authorization') == 'Bearer ' + state['token']
                self.send_response(200 if accepted else 401)
                rows = client.retrieve(body['dataset_ids'][0], body['document_ids'][0], body['question']) if accepted else []
                raw = json.dumps({'code': 0 if accepted else 401, 'data': {'chunks': [
                    {'id': r['id'], 'content': r['text'], 'document_id': r['documentId'],
                     'dataset_id': body['dataset_ids'][0]} for r in rows]}}).encode()
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    with listening(ThreadingHTTPServer(('127.0.0.1', 0), Handler)) as base:
        class Seed(Ragflow):
            def __init__(self, *_):
                # Only this test seed injects a controlled endpoint, not production.
                self.base, self.token = base, None
                self.opener = request.build_opener(NoRedirect())
                _, headers = self._http('POST', '/auth/login', {})
                self.token, self.model_id = headers['Authorization'], 'controlled'
        session = RagflowQuerySession(None, None, client_type=Seed)
        try:
            yield session, state
        finally:
            session.close()


def test_parallel_runtime_queries_share_one_login_not_authorization(ready):
    runtime, body, _, service, client = ready
    with rotating_upstream(client) as (session, state):
        runtime.client_factory = session
        state['barrier'] = threading.Barrier(2)
        with listening(IsolatedServer(('127.0.0.1', 0), handler(runtime))) as base:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(http, base, '/query', TOKEN,
                    {**body, 'requestId': 'parallel-' + str(i), 'traceId': 'trace-' + str(i)}) for i in range(2)]
                results = [f.result(timeout=10) for f in futures]
        assert all(status == 200 and result['decision'] == 'EVIDENCE_FOUND' for status, result in results)
        assert {result['receipt']['requestId'] for _, result in results} == {'parallel-0', 'parallel-1'}
        assert state['logins'] == session.login_attempts == 1 and state['retrievals'] == 2
        core = service.core()
        try: assert core.db.execute("SELECT count(*) FROM objects WHERE kind='document-receipt'").fetchone()[0] == 2
        finally: core.close()


@pytest.mark.parametrize('change', ['lease-revoked', 'lease-expired', 'source-permission', 'product-permission'])
def test_session_reuse_never_caches_host_or_core_grants(ready, change):
    runtime, body, current, service, client = ready
    with rotating_upstream(client) as (session, state):
        runtime.client_factory = session
        assert runtime.query(TOKEN, body)['decision'] == 'EVIDENCE_FOUND'
        if change == 'lease-revoked': current['lease'] = None
        elif change == 'lease-expired':
            current['lease'] = replace(current['lease'], expires=datetime.now(timezone.utc) - timedelta(seconds=1))
        else:
            core = service.core()
            try:
                revision, sha = core._head(AUTHOR, 'policy', 'current')
                policy = core._get(AUTHOR, sha, 'active-policy')
                prefix = 'source:' if change == 'source-permission' else 'product:'
                policy['grants'] = [g for g in policy['grants'] if not
                    (g['principal'] == READER.principal and g['resource'].startswith(prefix))]
                policy['revision'] = revision + 1
                core.set_policy(AUTHOR, policy, revision)
            finally: core.close()
        with pytest.raises(Rejected): runtime.query(TOKEN, {**body, 'requestId': 'after-revocation'})
        assert state['retrievals'] == state['logins'] == session.login_attempts == 1


def test_upstream_401_is_terminal_without_login_or_query_retry(ready):
    runtime, body, _, _, client = ready
    with rotating_upstream(client) as (session, state):
        runtime.client_factory = session
        assert runtime.query(TOKEN, body)['decision'] == 'EVIDENCE_FOUND'
        state['token'] = 'external-login-invalidated-old-session'
        with pytest.raises(Rejected, match='RAGFLOW_UNAVAILABLE'):
            runtime.query(TOKEN, {**body, 'requestId': 'expired-upstream'})
        with pytest.raises(Rejected, match='RAGFLOW_UNAVAILABLE'):
            runtime.query(TOKEN, {**body, 'requestId': 'not-retried'})
        assert state['logins'] == session.login_attempts == 1
        assert state['retrievals'] == 2


def test_login_failure_is_not_retried(ready):
    with rotating_upstream(ready[4]) as (session, state):
        state['login_failure'] = True
        for _ in range(2):
            with pytest.raises(Rejected, match='RAGFLOW_UNAVAILABLE'): session()
        assert state['logins'] == session.login_attempts == 1
        assert state['retrievals'] == 0


def test_clients_have_independent_transport_and_session_close_fails_closed(ready):
    with rotating_upstream(ready[4]) as (session, state):
        first, second = session(), session()
        assert first is not second and first.opener is not second.opener
        first.close()
        assert first.token is None and second.token is not None
        with pytest.raises(Rejected): first._http('POST', '/retrieval', {})
        session.close()
        with pytest.raises(Rejected): second._http('POST', '/retrieval', {})
        with pytest.raises(Rejected): session()
        second.close()
        assert second.token is None and state['retrievals'] == 0


@pytest.mark.parametrize('change', ['lease', 'core'])
def test_final_authorization_still_checked_after_shared_session_retrieval(ready, change):
    runtime, body, current, service, client = ready
    with rotating_upstream(client) as (session, state):
        runtime.client_factory = session
        def revoke():
            if change == 'lease': current['lease'] = None
            else:
                core = service.core()
                try: core.set_policy(AUTHOR, {'schemaVersion': 'active-policy.v0.1', 'revision': 2, 'grants': []}, 1)
                finally: core.close()
        state['callback'] = revoke
        with pytest.raises(Rejected): runtime.query(TOKEN, body)
        assert state['logins'] == state['retrievals'] == 1
