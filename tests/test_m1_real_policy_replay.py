"""Retained evidence checks; no network, no new scoring or model calls."""
import json
from pathlib import Path

import pytest

from knowledge_core.contracts import digest
from knowledge_core.rules import evaluate
from probes.documents.anchor_bridge import bind_rule_evidence
from probes.llm.linked import decode_envelope, convert

ROOT = Path(__file__).parents[1] / 'evidence/m1-round3'


@pytest.mark.parametrize('name,case,passed', [
    ('full-clause', 'P43', False), ('full-clause', 'P08', False),
    ('full-clause', 'P33', True), ('narrow-input', 'P43-NARROW', False),
    ('bounded-fields', 'P43-BOUND-FIELDS', True),
])
def test_all_real_attempts_replay_without_rewriting_gold(name, case, passed):
    record = json.loads((ROOT / 'policy' / name / (case + '.json')).read_text())
    raw = (ROOT / 'sources/regulation.html').read_bytes()
    rules = record['ir']
    assert record['assessment']['passed'] is passed
    envelope, fmt = decode_envelope(record['response']['choices'][0]['message']['content'])
    assert fmt == record['format']
    assert convert(envelope, record['derivedSource'], rules['fields'], rules['rules'][0]['scope']) == rules
    assert bind_rule_evidence(raw, record['derivedSource'], record['bridge'], rules) == record['binding']
    assert record['binding']['ruleIrDigest'] == digest(rules)
    for check in record['assessment']['checks']:
        assert evaluate(rules, check['ruleId'], check['inputs'], check['host'])['decision'] == check['actual']


def test_bounded_fields_do_not_silently_repair_previous_model():
    old = json.loads((ROOT / 'policy/narrow-input/P43-NARROW.json').read_text())
    new = json.loads((ROOT / 'policy/bounded-fields/P43-BOUND-FIELDS.json').read_text())
    assert old['requestDigest'] != new['requestDigest']
    assert old['derivedSource']['content'] == new['derivedSource']['content']
    assert {f['path'] for f in new['ir']['fields']} == {'original_months', 'extension_months'}
    assert old['assessment']['checks'][0]['actual'] == 'UNKNOWN'
    assert new['assessment']['checks'][0]['actual'] == 'MET'
