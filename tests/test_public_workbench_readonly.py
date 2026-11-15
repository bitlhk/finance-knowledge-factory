import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from web_production.server import handler


class NoBusinessCalls:
    m2 = True

    def __getattr__(self, name):
        raise AssertionError('Public request accessed business service: ' + name)


@pytest.fixture
def public_server(monkeypatch):
    monkeypatch.delenv('KF_WORKBENCH_ACCESS', raising=False)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(NoBusinessCalls()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize('path', [
    '/api/sources', '/api/runs', '/api/sample', '/api/document-evaluate',
    '/api/document-source-activate', '/api/document-approve', '/api/document-publish',
    '/api/search', '/api/rule-test', '/api/business-samples/boc-amsylj01',
    '/api/business-products/cmbwm-132112/import', '/api/future-write',
])
def test_same_origin_post_denied_before_any_service_call(public_server, path):
    req = Request(public_server + path, data=b'{"title":"must not be stored"}',
                  headers={'Content-Type': 'application/json', 'Origin': public_server,
                           'X-Role': 'publisher', 'X-Forwarded-For': '127.0.0.1',
                           'Authorization': 'Bearer not-a-maintenance-grant'})
    with pytest.raises(HTTPError) as error:
        urlopen(req)
    assert error.value.code == 403
    assert json.load(error.value)['error'] == 'PUBLIC_WORKBENCH_READ_ONLY'


def test_public_state_does_not_read_shared_workspace_or_restore_test_tasks(public_server):
    state = json.load(urlopen(public_server + '/api/state'))
    assert state['accessMode'] == 'PUBLIC_READ_ONLY'
    assert state['sources'] == state['runs'] == state['isolatedReleases'] == []
    assert state['modelReady'] is False
    with pytest.raises(HTTPError) as error:
        urlopen(public_server + '/api/runs/any-shared-test-id')
    assert error.value.code == 403
    assert urlopen(public_server + '/').status == 200


def test_post_invalid_body_cannot_change_denial(public_server):
    with pytest.raises(HTTPError) as error:
        urlopen(Request(public_server + '/api/sources', data=b'not json'))
    assert error.value.code == 403
