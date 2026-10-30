import copy
import json
from pathlib import Path

import pytest

from probes.flowable.compiler import compile_rule, prepare
from probes.llm.run import check
from knowledge_core.contracts import Rejected
from tests.support import CASES, CONTEXT, ir


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_flowable_guard_never_evaluates_eligible_predicate(case):
    rules = ir()
    compiled = compile_rule(rules, case["ruleId"])
    prepared = prepare(rules, case["ruleId"], case["inputs"], {**CONTEXT.facts(), **case.get("host", {})}, compiled)
    if "guard" in prepared:
        assert prepared["guard"] == case["expected"]
    else:
        assert set(prepared) == {"variables"}
        assert prepared["variables"]
    assert "hitPolicy=\"UNIQUE\"" in compiled["xml"]


def test_compiler_does_not_embed_external_enum_values():
    rules = ir()
    dangerous = "${''.getClass()}<unexpected>"
    rules["fields"][2]["values"].append(dangerous)
    rules["rules"][0]["exceptions"][0]["when"]["right"]["literal"]["value"] = dangerous
    compiled = compile_rule(rules, "age")
    assert dangerous not in compiled["xml"]
    assert any(s.get("literal", {}).get("value") == dangerous for s in compiled["slots"])


def test_parameterized_xml_is_not_a_complete_version_identity():
    old = ir()
    new = copy.deepcopy(old)
    new["revision"] = 2
    new["rules"][1]["predicate"]["right"]["literal"]["value"] = 12
    first, second = compile_rule(old, "months"), compile_rule(new, "months")
    assert first["dmnDigest"] == second["dmnDigest"]
    assert first["compiledDigest"] != second["compiledDigest"]
    with pytest.raises(Rejected, match="COMPILED_BINDING_MISMATCH"):
        prepare(new, "months", {"months": 24}, CONTEXT.facts(), first)


def test_model_output_never_grants_publication():
    cases = json.loads((Path(__file__).parents[1] / "probes/llm/cases.json").read_text())
    case = cases[0]
    output = {"status": "CANDIDATE", "conditions": [{**case["condition"], "quote": "申请期限不得超过36个月"}],
              "exceptionQuotes": [], "scopeQuotes": [], "referenceQuotes": [], "unresolvedQuotes": []}
    assert check(case, output) == {"passed": True, "failures": [], "publicationAllowed": False}
    bad = copy.deepcopy(output)
    bad["conditions"][0]["value"] = True
    assert not check(case, bad)["passed"]
    bad = copy.deepcopy(output)
    bad["conditions"][0]["quote"] = "用户未提供的条件"
    assert "UNSUPPORTED_QUOTE" in check(case, bad)["failures"]
    assert not check(cases[1], output)["passed"]
