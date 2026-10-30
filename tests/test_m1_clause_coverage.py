import copy
import json
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected, digest
from knowledge_core.rules import evaluate
from probes.documents.anchor_bridge import build
from probes.llm.coverage import assess_coverage, project, validate_coverage
from probes.llm.coverage_gold import GOLD
from probes.llm.coverage_recipe import RECIPE, FIELDS, SCOPE, messages
from probes.llm.policy_gold import HOST


ROOT = Path(__file__).parents[1]


def fixture(case="P43"):
    """Hand-built oracle fixture, never presented as model-produced output."""
    raw = (ROOT / "evidence/m1-round3/sources/regulation.html").read_bytes()
    chunks = json.loads((ROOT / "evidence/m1-round2/html-comparison.json").read_text())["results"]["docling"]["chunks"]
    source, bridge = build(raw, [c for c in chunks if c["clause"] == GOLD[case]["clause"]], "coverage-" + case)
    coverage = {"units": [{"id": u["key"], "quote": u["needles"][0],
                            **{k: copy.deepcopy(u[k]) for k in ("kind", "state", "predicate", "appliesWhen")}}
                           for u in GOLD[case]["units"]],
                "relations": [{"from": a, "type": t, "to": b} for a, t, b in GOLD[case]["relations"]]}
    return raw, source, bridge, coverage


@pytest.mark.parametrize("case", list(GOLD))
def test_oracle_fixtures_cover_frozen_semantics(case):
    _, source, _, coverage = fixture(case)
    assert assess_coverage(coverage, source, GOLD[case])["passed"]
    projection = project(coverage, source, FIELDS, SCOPE)
    assert projection["publicationAllowed"] is False
    assert projection["wholeClauseDecision"] == "NOT_EVALUATED"
    if not GOLD[case]["execution"]:
        assert projection["ir"] is None


def test_numeric_met_is_not_whole_clause_met():
    _, source, _, coverage = fixture()
    projected = project(coverage, source, FIELDS, SCOPE)
    for gold in GOLD["P43"]["execution"]["short"]:
        result = evaluate(projected["ir"], "short", gold["inputs"], {**HOST, **gold.get("host", {})})
        assert result["decision"] == gold["expected"]
    assert len(projected["slices"]) == 1
    assert projected["slices"][0]["resultScope"] == "SUBCONDITION_ONLY"
    assert len(coverage["units"]) == 7


@pytest.mark.parametrize("damage", ["cashflow_wrong_branch", "drop_dependency", "drop_followup", "swap_field", "fake_executable"])
def test_semantic_mutations_cannot_pass(damage):
    case = "P08" if damage in ("cashflow_wrong_branch", "drop_dependency") else "P43"
    _, source, _, coverage = fixture(case)
    if damage == "cashflow_wrong_branch":
        next(r for r in coverage["relations"] if r["to"] == "cashflow")["from"] = "consumption"
    elif damage == "drop_dependency":
        coverage["relations"] = [r for r in coverage["relations"] if r["to"] != "national"]
    elif damage == "drop_followup":
        coverage["units"] = [u for u in coverage["units"] if u["id"] != "management"]
        coverage["relations"] = [r for r in coverage["relations"] if r["to"] != "management"]
    elif damage == "swap_field":
        next(u for u in coverage["units"] if u["id"] == "short")["predicate"]["right"] = {"field": "months"}
    else:
        u = next(u for u in coverage["units"] if u["id"] == "long")
        u["state"] = "EXECUTABLE"
        u["predicate"] = copy.deepcopy(next(u for u in coverage["units"] if u["id"] == "short")["predicate"])
    assert not assess_coverage(coverage, source, GOLD[case])["passed"]


def test_same_review_outcomes_do_not_hide_misbound_cashflow():
    _, source, _, coverage = fixture("P08")
    next(r for r in coverage["relations"] if r["to"] == "cashflow")["from"] = "consumption"
    ir = project(coverage, source, FIELDS, SCOPE)["ir"]
    assert all(evaluate(ir, r["id"], {"purpose_kind": "BUSINESS", "months": 120}, HOST)["decision"] == "REVIEW_REQUIRED" for r in ir["rules"])
    assert not assess_coverage(coverage, source, GOLD["P08"])["passed"]


def test_ir_strict_unknown_safety_is_unchanged():
    _, source, _, coverage = fixture("P08")
    ir = project(coverage, source, FIELDS, SCOPE)["ir"]
    ceiling = next(r for r in ir["rules"] if r["id"] == "ceiling")
    assert any("经营现金流" in u["reason"] for u in ceiling["unresolved"])
    assert evaluate(ir, "ceiling", {"purpose_kind": "BUSINESS", "months": 120}, HOST)["decision"] == "REVIEW_REQUIRED"


def test_renamed_ids_and_reversed_symmetric_edges_are_not_failures():
    _, source, _, coverage = fixture()
    for u in coverage["units"]:
        u["id"] = "renamed-" + u["id"]
    for r in coverage["relations"]:
        r["from"], r["to"] = "renamed-" + r["from"], "renamed-" + r["to"]
        if r["type"] == "alternative_to":
            r["from"], r["to"] = r["to"], r["from"]
    assert assess_coverage(coverage, source, GOLD["P43"])["passed"]


@pytest.mark.parametrize("damage", ["quote", "duplicate", "unknown_relation", "cycle", "blank"])
def test_malformed_or_unsupported_coverage_rejected(damage):
    _, source, _, coverage = fixture()
    if damage == "quote":
        coverage["units"][0]["quote"] = "并不存在的条款"
    elif damage == "duplicate":
        coverage["units"][0]["id"] = coverage["units"][1]["id"]
    elif damage == "unknown_relation":
        coverage["relations"][0]["to"] = "missing"
    elif damage == "blank":
        coverage["units"][0]["quote"] = " "
    else:
        coverage["relations"] += [{"from": "short", "type": "requires", "to": "long"},
                                   {"from": "long", "type": "requires", "to": "short"}]
    with pytest.raises(Rejected):
        project(coverage, source, FIELDS, SCOPE)


def test_gold_not_in_model_payload_and_no_silent_truncation():
    _, source, _, _ = fixture()
    payload = messages(RECIPE, source)
    assert payload[1]["content"] == source["content"]
    assert "expectedRuleCount" not in json.dumps(payload)
    assert "gold" not in payload[0]["content"].lower()
    assert "第四十三条" not in payload[0]["content"]
    with pytest.raises(Rejected, match="SOURCE_BUDGET"):
        messages(RECIPE, {"content": "x" * 20001})
