import hashlib
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
    page = reader.page('000343', 1)
    assert page['page']['text'] == 'Original'
    assert page['archivedPageCount'] == 1
    assert 'totalPages' not in page
    replay = reader.replay('000343')
    assert replay['readOnly'] is True
    assert len(replay['stages']) == 5
    assert replay['stages'][1]['evidence'] == {'archivedPageCount': 1}
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


def test_archived_page_count_is_not_pdf_page_count(tmp_path):
    config = fixture_catalog(tmp_path)
    provenance_path = tmp_path / 'provenance.json'
    provenance = json.loads(provenance_path.read_text())
    provenance['pageCount'] = 200
    provenance['sourceFiles'][0]['pageCount'] = 200
    provenance_path.write_text(json.dumps(provenance))
    config_path = tmp_path / 'catalog.json'
    configuration = json.loads(config_path.read_text())
    configuration['products'][0]['provenanceSha256'] = hashlib.sha256(
        provenance_path.read_bytes()).hexdigest()
    config_path.write_text(json.dumps(configuration))
    reader = PublicReader(config)
    assert reader.summary('000343')['sources'][0]['pageCount'] == 200
    assert reader.page('000343', 1)['archivedPageCount'] == 1
    assert reader.replay('000343')['stages'][1]['evidence']['archivedPageCount'] == 1


def test_aggregate_limit_is_bounded_and_recovers(caplog):
    now = [0]
    reader = PublicReader(None, clock=lambda: now[0], limit=2)
    assert reader.admit() and reader.admit()
    assert not reader.admit()
    assert reader.rejected_total == reader.rejected_window == 1
    assert 'rejected_total=1 rejected_window=1' in caplog.text
    now[0] = 60
    assert reader.admit()
    assert reader.rejected_total == 1 and reader.rejected_window == 0


def test_http_pagination_validation_and_readonly_replay(tmp_path, monkeypatch):
    monkeypatch.setenv('KF_WORKBENCH_CATALOG', fixture_catalog(tmp_path))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(NoBusinessCalls(), read_only=True))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/api/published-products/000343'
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        for _ in range(121):
            urlopen(base + '/api/state').close()
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
        assert urlopen(base + '/api/state').status == 200
        assert urlopen(base + '/').status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
