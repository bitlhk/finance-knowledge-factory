import copy
import json

import pytest

from knowledge_core.contracts import Rejected
from probes.documents.anchor_bridge import bind_rule_evidence
from probes.flowable.compiler import compile_rule
from probes.llm.candidate_bundle import REQUIRED, evidence_digest, seal, verify
from probes.llm.coverage import assess_coverage, project
from probes.llm.coverage_gold import GOLD
from probes.llm.coverage_recipe import RECIPE, FIELDS, SCOPE, messages
from tests.test_m1_clause_coverage import fixture


def parts():
    raw, source, bridge, coverage = fixture()
    projection = project(coverage, source, FIELDS, SCOPE)
    ir = projection["ir"]
    return raw, {"source": source, "bridge": bridge, "recipe": RECIPE,
                 "request": {"model": "test-not-real", "temperature": 0.1, "messages": messages(RECIPE, source)},
                 "response": {"choices": [{"message": {"content": json.dumps(coverage)}}]},
                 "coverage": coverage, "projection": projection, "gold": GOLD["P43"],
                 "assessment": assess_coverage(coverage, source, GOLD["P43"]),
                 "compiled": [compile_rule(ir, r["id"]) for r in ir["rules"]],
                 "binding": bind_rule_evidence(raw, source, bridge, ir),
                 "execution": {"status": "NOT_RUN"}}


def test_complete_bundle_is_verifiable_not_a_release():
    raw, p = parts()
    manifest = seal(raw, p)
    assert verify(raw, p, manifest)
    assert manifest["publicationAllowed"] is False
    assert manifest["parts"]["request"] == evidence_digest(p["request"])


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_missing_or_modified_component_fails(name):
    raw, p = parts()
    manifest = seal(raw, p)
    changed = copy.deepcopy(p)
    changed[name] = None
    with pytest.raises(Rejected):
        verify(raw, changed, manifest)
    del changed[name]
    with pytest.raises(Rejected):
        seal(raw, changed)


@pytest.mark.parametrize("name", ["request", "response", "projection", "assessment", "compiled", "binding"])
def test_resealing_mismatched_artifacts_does_not_fix_provenance(name):
    raw, p = parts()
    p = copy.deepcopy(p)
    if name == "request":
        p[name]["messages"][1]["content"] = "another source"
    elif name == "response":
        other = copy.deepcopy(p["coverage"])
        other["units"][0]["state"] = "EXTERNAL"
        p[name]["choices"][0]["message"]["content"] = json.dumps(other)
    elif name == "projection":
        p[name]["slices"] = []
    elif name == "assessment":
        p[name]["passed"] = False
    elif name == "compiled":
        p[name][0]["xml"] += "tampered"
    else:
        p[name]["bindings"] = []
    with pytest.raises(Rejected):
        verify(raw, p, seal(raw, p))


def test_wrong_original_source_rejected_even_after_reseal():
    raw, p = parts()
    with pytest.raises(Rejected):
        verify(raw + b" ", p, seal(raw + b" ", p))


def test_nonfinite_request_parameters_are_not_hashable():
    with pytest.raises(ValueError):
        evidence_digest({"temperature": float("nan")})
