import copy
import json
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.rules import evaluate
from probes.llm.coverage_gold_v2 import GOLD, PROVENANCE
from probes.llm.coverage_review_v2 import assess
from probes.llm.linked import decode_envelope, source
from probes.llm.policy_gold import HOST
from probes.llm.semantic_v2 import RECIPE, validate
from probes.llm.verified_lowering import inspect_legacy, lower, recognize
from tests.test_m1_clause_coverage import fixture


def unit(quote, branch=None, kind="CONDITION", state="PROPOSED_NUMERIC", key="u"):
    return {"id": key, "kind": kind, "state": state, "quote": quote, "branchQuote": branch}


def payload(u):
    return {"units": [u], "relations": []}


def test_verified_field_comparison_uses_source_not_model_formula():
    _, src, _, old = fixture()
    quote = next(u["quote"] for u in old["units"] if u["id"] == "short")
    result = lower(payload(unit(quote)), src)
    assert result["ir"]["rules"][0]["predicate"]["right"] == {"field": "original_months"}
    for case in GOLD["P43"]["execution"]["short"]:
        assert evaluate(result["ir"], "u", case["inputs"], {**HOST, **case.get("host", {})})["decision"] == case["expected"]
    assert result["wholeClauseDecision"] == "REVIEW_REQUIRED"
    assert not result["publicationAllowed"]


@pytest.mark.parametrize("quote", ["同意展期的", "借款人申请贷款展期的",
    "期限超过一年的贷款展期期限累计不得超过原贷款期限的一半"])
def test_no_model_numeric_claim_authorizes_unsupported_meanings(quote):
    _, src, _, _ = fixture()
    result = lower(payload(unit(quote)), src)
    assert result["ir"] is None
    assert result["decisions"][0]["status"] in ("UNSUPPORTED", "UNVERIFIABLE")


@pytest.mark.parametrize("change", ["predicate", "appliesWhen", "EXECUTABLE", "digest", "branch", "quote", "unknown_edge"])
def test_untrusted_formulas_and_broken_evidence_rejected(change):
    quote = "用于个人消费的贷款期限不得超过五年"
    src = source(quote, "isolated-test")
    output = payload(unit(quote, "用于个人消费"))
    u = output["units"][0]
    if change in ("predicate", "appliesWhen"):
        u[change] = {"op": "lte", "left": {"field": "months"}, "right": {"literal": {"type": "integer", "value": 0}}}
    elif change == "EXECUTABLE":
        u["state"] = "EXECUTABLE"
    elif change == "digest":
        src["content"] += "x"
    elif change == "branch":
        u["branchQuote"] = "nonexistent"
    elif change == "quote":
        u["quote"] = "nonexistent"
    else:
        output["relations"] = [{"from": "u", "to": "absent", "type": "requires"}]
    with pytest.raises(Rejected):
        lower(output, src)


@pytest.mark.parametrize("damage", ["constant_zero", "wrong_operand", "wrong_boundary"])
def test_saved_formula_proposals_cannot_override_source(damage):
    _, src, _, old = fixture()
    u = copy.deepcopy(next(u for u in old["units"] if u["id"] == "short"))
    if damage == "constant_zero":
        u["predicate"]["right"] = {"literal": {"type": "integer", "value": 0}}
    elif damage == "wrong_operand":
        u["predicate"]["right"] = {"field": "months"}
    else:
        u["appliesWhen"]["op"] = "lt"
    assert inspect_legacy(u, src)["status"] == "REJECTED_FORMULA"


def test_actual_legacy_errors_rejected_without_changing_scores():
    root = Path(__file__).parents[1] / "evidence/m1-round4"
    frozen = json.loads((root / "frozen.json").read_text())
    for name in ("P43-1", "P43-2"):
        record = json.loads((root / "attempts" / (name + ".json")).read_text())
        output, _ = decode_envelope(record["response"]["choices"][0]["message"]["content"])
        bad = [u for u in output["units"] if u["predicate"] and ("一半" in u["quote"] or u["quote"] == "同意展期的")]
        assert bad
        assert all(inspect_legacy(u, frozen["sources"]["P43"]["source"])["status"] == "REJECTED_FORMULA" for u in bad)


def test_general_duration_does_not_become_unconditional_permission():
    _, src, _, old = fixture("P08")
    quote = next(u["quote"] for u in old["units"] if u["id"] == "business")
    result = lower(payload(unit(quote, "用于生产经营")), src)
    assert len(result["ir"]["rules"][0]["unresolved"]) == 2
    assert evaluate(result["ir"], "u", {"purpose_kind": "BUSINESS", "months": 60}, HOST)["decision"] == "REVIEW_REQUIRED"
    ceiling = lower(payload(unit("最长不超过十年", "用于生产经营")), src)
    assert ceiling["ir"] is None


def test_wrong_branch_not_repaired_silently():
    _, src, _, _ = fixture("P08")
    result = lower(payload(unit("用于个人消费的贷款期限不得超过五年", "用于生产经营")), src)
    assert result["ir"] is None
    assert result["decisions"][0]["reason"] == "BRANCH_BINDING_NOT_CONFIRMED"


@pytest.mark.parametrize("text", ["六年", "24年"])
def test_templates_not_specific_to_existing_thresholds(text):
    quote = "用于个人消费的贷款期限不得超过" + text
    result = lower(payload(unit(quote, "用于个人消费")), source(quote, "new-text"))
    assert result["ir"]["rules"][0]["predicate"]["right"]["literal"]["value"] == (72 if text == "六年" else 288)


def test_partial_statement_rejected():
    quote = "用于个人消费的贷款期限不得超过五年"
    assert recognize(quote, source("不适用" + quote, "partial"))["status"] != "VERIFIED_NUMERIC"


def test_gold_not_prompt_and_old_results_unchanged():
    assert "第四十三条" not in json.dumps(RECIPE, ensure_ascii=False)
    assert "expected" not in json.dumps(RECIPE)
    assert PROVENANCE["postObservationRevision"]
    assert not PROVENANCE["businessOwnerApproved"]
    assert GOLD["P43"]["atoms"][0]["key"] == "trigger"
    assert ["extension", "exception_to", "business"] in GOLD["P08"]["relations"]


def test_merged_conditional_meanings_can_be_checked_without_count_matching():
    _, src, _, _ = fixture("P08")
    quote = "对于贷款用途对应的经营现金流回收周期较长的，可适当延长贷款期限"
    output = payload(unit(quote, "用于生产经营", "QUALIFIER", "MANUAL"))
    gold = {"atoms": [a for a in GOLD["P08"]["atoms"] if a["key"] in ("cashflow", "extension")],
            "relations": [["extension", "requires", "cashflow"]],
            "embeddedRelations": GOLD["P08"]["embeddedRelations"]}
    result = assess(output, src, gold)
    assert result["status"] == "AUTOMATED_COVERAGE_MATCH"
    assert result["atomicEvidenceCount"] == 2
    output["units"][0]["branchQuote"] = "用于个人消费"
    assert assess(output, src, gold)["status"] == "SEMANTIC_ERROR"
    output["units"][0]["branchQuote"] = None
    assert assess(output, src, gold)["status"] == "REVIEW_REQUIRED"


def test_kind_difference_is_not_pass_or_automatic_fact_error():
    quote = "借款人申请贷款展期的"
    output = payload(unit(quote, kind="CONDITION", state="MANUAL"))
    gold = {"atoms": [GOLD["P43"]["atoms"][0]], "relations": [], "embeddedRelations": []}
    result = assess(output, source(quote, "trigger-test"), gold)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["findings"][0]["category"] == "REPRESENTATION_DIFFERENCE"
