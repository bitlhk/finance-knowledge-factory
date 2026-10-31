import copy

import pytest

from knowledge_core.contracts import Rejected, digest, text_digest
from knowledge_core.evidence.anchor_bridge import build, bind_rule_evidence, resolve, verify_bridge, select_quote
from knowledge_core.evidence.html_evidence import locate


RAW = '<html><body><p>第一条  期限不超过十二个月。</p><p>第二条  另有规定的除外。</p></body></html>'.encode()


def fixture():
    chunks = locate(RAW, ['第一条  期限不超过十二个月。 第二条  另有规定的除外。'])
    return build(RAW, chunks, 'original-derived')


def test_bridge_roundtrip_and_explicit_line_space():
    src, bridge = fixture()
    verify_bridge(RAW, src, bridge, digest(bridge))
    assert bridge['lineSpace'] == 'DERIVED_TEXT_ONLY'
    assert bridge['sourceBytesDigest'] != digest(src)
    ref = {'sourceDigest': digest(src), 'lineStart': 1, 'lineEnd': 1,
           'quoteDigest': text_digest(src['content'].splitlines()[0])}
    assert resolve(RAW, src, bridge, digest(bridge), ref) == [bridge['mappings'][0]['anchorId']]


@pytest.mark.parametrize('part', ['original', 'derived', 'bridge', 'quote', 'coverage', 'anchor_id'])
def test_changed_evidence_rejected(part):
    src, bridge = fixture()
    expected = digest(bridge)
    raw = RAW
    if part == 'original': raw += b' '
    if part == 'derived': src['content'] += 'changed'
    if part == 'bridge': bridge['producer'] = 'other'
    if part == 'quote':
        bridge['mappings'][0]['anchor']['quote'] = 'invented'
        expected = digest(bridge)
    if part == 'coverage':
        bridge['mappings'][0]['lineStart'] = 2
        expected = digest(bridge)
    if part == 'anchor_id':
        bridge['mappings'][0]['anchorId'] = '0' * 64
        expected = digest(bridge)
    with pytest.raises(Rejected): verify_bridge(raw, src, bridge, expected)


@pytest.mark.parametrize('change', ['digest', 'zero', 'boolean', 'quote', 'overflow'])
def test_legacy_ref_cannot_fake_original_location(change):
    src, bridge = fixture()
    ref = {'sourceDigest': digest(src), 'lineStart': 1, 'lineEnd': 1,
           'quoteDigest': text_digest(src['content'].splitlines()[0])}
    if change == 'digest': ref['sourceDigest'] = bridge['sourceBytesDigest']
    if change == 'zero': ref['lineStart'] = 0
    if change == 'boolean': ref['lineStart'] = True
    if change == 'quote': ref['quoteDigest'] = '0' * 64
    if change == 'overflow': ref['lineEnd'] = 99
    with pytest.raises(Rejected): resolve(RAW, src, bridge, digest(bridge), ref)


def test_same_path_different_bytes_has_different_anchor_id():
    source, bridge = fixture()
    changed = RAW.replace('十二'.encode(), '十三'.encode())
    other = build(changed, locate(changed, ['第一条  期限不超过十三个月。 第二条  另有规定的除外。']), 'original-derived')
    assert bridge['mappings'][0]['anchorId'] != other[1]['mappings'][0]['anchorId']


def test_duplicate_anchor_rejected():
    chunk = locate(RAW, ['第一条  期限不超过十二个月。 第二条  另有规定的除外。'])[0]
    with pytest.raises(Rejected): build(RAW, [chunk, chunk], 'original-derived')


def test_explicit_subclause_retains_original_location():
    chunk = locate(RAW, ['第一条  期限不超过十二个月。 第二条  另有规定的除外。'])[0]
    selected = select_quote(RAW, chunk, '期限不超过十二个月')
    assert selected['anchors'][0]['start'] > chunk['anchors'][0]['start']
    src, bridge = build(RAW, [selected], 'selected')
    verify_bridge(RAW, src, bridge, digest(bridge))
    assert src['content'] == '期限不超过十二个月'


@pytest.mark.parametrize('quote', ['', '不存在', '期限\n不超过'])
def test_invalid_subclause_rejected(quote):
    chunk = locate(RAW, ['第一条  期限不超过十二个月。 第二条  另有规定的除外。'])[0]
    with pytest.raises(Rejected): select_quote(RAW, chunk, quote)


def test_repeated_subclause_rejected():
    raw = '<p>第一条 条件，条件。</p>'.encode()
    chunk = locate(raw, ['第一条 条件，条件。'])[0]
    with pytest.raises(Rejected): select_quote(raw, chunk, '条件')
