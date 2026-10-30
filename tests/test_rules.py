import copy

import pytest

from knowledge_core.contracts import Rejected, strict_date
from knowledge_core.rules import evaluate, validate_ir
from tests.support import CASES, CONTEXT, ir


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_frozen_rule_cases(case):
    result = evaluate(ir(), case["ruleId"], case["inputs"], {**CONTEXT.facts(), **case.get("host", {})})
    assert result["decision"] == case["expected"]


@pytest.mark.parametrize("value", [1.5, 0.0, False, True, "36", [], {}, -1, 121])
def test_integer_never_coerced(value):
    assert evaluate(ir(), "months", {"months": value}, CONTEXT.facts())["decision"] == "INVALID_INPUT"


@pytest.mark.parametrize("value", ["2023-02-30", "2026-13-01", "2026-1-01", "20260101", "2026-11-15T00:00:00Z", True, 20261115])
def test_strict_calendar(value):
    with pytest.raises(Rejected, match="INVALID_DATE"):
        strict_date(value)


def test_unresolved_candidate_never_met():
    rules = ir()
    rules["rules"][0]["unresolved"] = [{"reason": "Exception not modeled", "evidenceRef": rules["rules"][0]["evidenceRefs"][0]}]
    assert evaluate(rules, "age", {"registration_date": "2020-01-01", "industry": "ordinary"}, CONTEXT.facts())["decision"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("mutation", [
    lambda r: r["rules"][0].update(predicate={"op": "eval", "code": "danger()"}),
    lambda r: r.update(externalSchema="https://example.org/remote"),
    lambda r: r["rules"][1]["predicate"]["right"].update(literal={"type": "boolean", "value": True}),
    lambda r: r["rules"][0]["predicate"]["start"].update(field="unregistered"),
    lambda r: r["rules"][0]["scope"].update(validTo="2025-01-01"),
    lambda r: r["rules"][0]["exceptions"][0].update(outcome="MET"),
    lambda r: r["fields"][1].update(sourceKind="INPUT"),
    lambda r: r["fields"][3].update(type="decimal"),
    lambda r: r["rules"].append(copy.deepcopy(r["rules"][0])),
])
def test_invalid_ir_rejected(mutation):
    rules = ir()
    mutation(rules)
    with pytest.raises(Rejected):
        validate_ir(rules)


def test_bounded_expression_depth():
    rules = ir()
    expression = rules["rules"][1]["predicate"]
    for _ in range(4):
        expression = {"op": "not", "arg": expression}
    rules["rules"][1]["predicate"] = expression
    with pytest.raises(Rejected, match="UNSUPPORTED_COMPLEXITY"):
        validate_ir(rules)


def test_boolean_short_circuit_cannot_hide_missing_input():
    rules = ir()
    rules["rules"][1]["predicate"] = {"op": "any", "args": [rules["rules"][1]["predicate"], rules["rules"][2]["predicate"]]}
    assert evaluate(rules, "months", {"months": 1}, CONTEXT.facts())["decision"] == "UNKNOWN"


def test_all_not_and_membership():
    rules = ir()
    rules["rules"][1]["predicate"] = {"op": "all", "args": [
        {"op": "in", "value": {"field": "months"}, "set": [{"type": "integer", "value": 36}]},
        {"op": "not", "arg": {"op": "eq", "left": {"field": "license_valid"}, "right": {"literal": {"type": "boolean", "value": False}}}}]}
    assert evaluate(rules, "months", {"months": 36, "license_valid": True}, CONTEXT.facts())["decision"] == "MET"
