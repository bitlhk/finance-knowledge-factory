import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from knowledge_core.contracts import Rejected
from tests.test_published_workbench import fixture_catalog
from tests.test_public_workbench_readonly import NoBusinessCalls
from web_production.public_reader import PublicReader
from web_production.server import handler


def test_summary_page_and_replay_are_public_archive_only(tmp_path):
    reader = PublicReader(fixture_catalog(tmp_path))
    before = (tmp_path / 'core.sqlite').read_bytes()
    summary = reader.summary('000343')
    assert 'pages' not in summary
    assert summary['pageIndex'] == [{'sourceId': 'summary', 'page': 1, 'htmlId': 'page-1'}]
    assert reader.page('000343', 1)['page']['text'] == 'Original'
    replay = reader.replay('000343')
    assert replay['readOnly'] is True
    assert len(replay['stages']) == 5
    assert replay['manifestDigest'] == summary['manifestDigest']
    assert 'private-user' not in json.dumps(replay)
    assert str(tmp_path) not in json.dumps(replay)
    assert (tmp_path / 'core.sqlite').read_bytes() == before
    with pytest.raises(Rejected, match='PUBLICATION_PAGE_NOT_FOUND'):
        reader.page('000343', 2)


def test_cache_refresh_failure_does_not_serve_stale_snapshot(tmp_path):
    now = [0]
    reader = PublicReader(fixture_catalog(tmp_path), clock=lambda: now[0])
    first = reader.summary('000343')
    first['title'] = 'caller mutation'
    assert reader.summary('000343')['title'] == 'Public fund'
    (tmp_path / 'source.pdf').write_bytes(b'corrupt')
    now[0] = 16
    for _ in range(2):
        with pytest.raises(Rejected, match='PUBLICATION_RECORD_UNAVAILABLE'):
            reader.summary('000343')


def test_aggregate_limit_is_bounded_and_recovers():
    now = [0]
    reader = PublicReader(None, clock=lambda: now[0], limit=2)
    assert reader.admit() and reader.admit()
    assert not reader.admit()
    now[0] = 60
    assert reader.admit()


def test_http_pagination_validation_and_readonly_replay(tmp_path, monkeypatch):
    monkeypatch.setenv('KF_WORKBENCH_CATALOG', fixture_catalog(tmp_path))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(NoBusinessCalls(), read_only=True))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/api/published-products/000343'
    try:
        assert 'pages' not in json.load(urlopen(url))
        assert json.load(urlopen(url + '/pages?page=1'))['page']['text'] == 'Original'
        assert json.load(urlopen(url + '/replay'))['readOnly'] is True
        for query in ['', '?page=0', '?page=-1', '?page=1&page=2', '?page=abc', '?page=1&file=x']:
            with pytest.raises(HTTPError) as error:
                urlopen(url + '/pages' + query)
            assert error.value.code == 400
        for _ in range(111):
            urlopen(url).close()
        with pytest.raises(HTTPError) as error:
            urlopen(url)
        assert error.value.code == 429
        assert error.value.headers['Retry-After'] == '60'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
