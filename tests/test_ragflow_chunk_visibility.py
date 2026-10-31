"""Controlled index visibility tests, not a real production acceptance."""
import pytest

from knowledge_core.contracts import Rejected
from m2.ragflow import Ragflow


def chunk(i):
    return {'chunk_id': str(i), 'content_with_weight': 'clause ' + str(i)}


def client(monkeypatch, responses):
    clock = [0]
    monkeypatch.setattr('m2.ragflow.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('m2.ragflow.time.sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    obj = object.__new__(Ragflow)
    obj.operations = []
    iterator = iter(responses)
    obj._http = lambda method, path: (next(iterator), {})
    return obj


def test_waits_for_visible_stable_index(monkeypatch):
    full = {'total': 2, 'chunks': [chunk(1), chunk(2)]}
    obj = client(monkeypatch, [{'total': 0, 'chunks': []}, full, full])
    assert obj._ready_chunks('d', 'f') == full['chunks']
    assert [o['stable'] for o in obj.operations] == [False, False, True]


def test_pages_beyond_one_hundred(monkeypatch):
    pages = [{'total': 105, 'chunks': [chunk(i) for i in range(100)]},
             {'total': 105, 'chunks': [chunk(i) for i in range(100, 105)]}]
    obj = client(monkeypatch, pages * 2)
    assert len(obj._ready_chunks('d', 'f')) == 105


def test_never_publishes_partial_or_empty_index(monkeypatch):
    obj = client(monkeypatch, [{'total': 1, 'chunks': []}] * 16)
    with pytest.raises(Rejected, match='RAGFLOW_CHUNKS_INCOMPLETE'):
        obj._ready_chunks('d', 'f')
    assert len(obj.operations) == 16


def test_duplicate_cannot_fake_completeness(monkeypatch):
    obj = client(monkeypatch, [{'total': 2, 'chunks': [chunk(1), chunk(1)]}])
    with pytest.raises(Rejected, match='RAGFLOW_DUPLICATE_CHUNK'):
        obj._ready_chunks('d', 'f')


@pytest.mark.parametrize('payload', [None, {'total': True, 'chunks': []},
    {'total': 1001, 'chunks': []}, {'total': 1, 'chunks': [{'chunk_id': 'a'}]}])
def test_bad_responses_fail_closed(monkeypatch, payload):
    obj = client(monkeypatch, [payload])
    with pytest.raises(Rejected, match='RAGFLOW_RESPONSE_INVALID'):
        obj._ready_chunks('d', 'f')


def test_changed_contents_need_another_stable_read(monkeypatch):
    first = {'total': 1, 'chunks': [chunk(1)]}
    second = {'total': 1, 'chunks': [chunk(2)]}
    obj = client(monkeypatch, [first, second, second])
    assert obj._ready_chunks('d', 'f') == second['chunks']
    assert len(obj.operations) == 3
