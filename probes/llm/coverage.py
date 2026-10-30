"""M1-only clause coverage, independent scoring and bounded IR projection.

This is not a new M0 contract or an approval engine. Gold never enters extraction.
"""
import copy
import json

from jsonschema import Draft202012Validator

from knowledge_core.contracts import EXPR, EXPRESSION, ID, STR, Rejected, arr, obj, digest
from probes.llm.linked import convert


VERSION = "clause-coverage.v0.1"
KINDS = ["PRECONDITION", "CONDITION", "QUALIFIER", "FOLLOW_UP", "REFERENCE"]
STATES = ["EXECUTABLE", "MANUAL", "UNSUPPORTED", "EXTERNAL"]
RELATIONS = ["requires", "business_prerequisite", "alternative_to", "followed_by"]
NULL_EXPR = {"anyOf": [EXPR, {"type": "null"}]}
SCHEMA = obj({
    "units": arr(obj({"id": ID, "kind": {"enum": KINDS}, "quote": STR,
                      "state": {"enum": STATES}, "predicate": NULL_EXPR,
                      "appliesWhen": NULL_EXPR}), 1, 40),
    "relations": arr(obj({"from": ID, "to": ID, "type": {"enum": RELATIONS}}), 0, 100),
})
SCHEMA["$defs"] = {"expression": EXPRESSION}


def canonical(value):
    """Normalize commutative conjunctions, never infer missing business semantics."""
    if isinstance(value, list):
        return [canonical(v) for v in value]
    if isinstance(value, dict):
        result = {k: canonical(v) for k, v in value.items()}
        if result.get("op") in ("all", "any"):
            result["args"] = sorted(result["args"], key=lambda x: json.dumps(x, sort_keys=True))
        return result
    return value


def validate_coverage(coverage, source):
    encoded = json.dumps(coverage, ensure_ascii=False)
    if len(encoded) > 100000:
        raise Rejected("COVERAGE_TOO_LARGE")
    def bounded(v, depth=0):
        if depth > 24:
            raise Rejected("COVERAGE_TOO_DEEP")
        for child in v.values() if isinstance(v, dict) else v if isinstance(v, list) else []:
            bounded(child, depth + 1)
    bounded(coverage)
    if list(Draft202012Validator(SCHEMA).iter_errors(coverage)):
        raise Rejected("COVERAGE_SCHEMA_INVALID")
    units = {u["id"]: u for u in coverage["units"]}
    if len(units) != len(coverage["units"]):
        raise Rejected("COVERAGE_DUPLICATE_ID")
    for u in units.values():
        if not u["quote"].strip() or source["content"].count(u["quote"]) != 1:
            raise Rejected("COVERAGE_QUOTE_NOT_UNIQUE")
        if u["state"] == "EXECUTABLE":
            if u["kind"] != "CONDITION" or u["predicate"] is None:
                raise Rejected("EXECUTABLE_CONDITION_REQUIRED")
        elif u["predicate"] is not None:
            raise Rejected("UNSUPPORTED_PREDICATE_FORBIDDEN")
    seen = set()
    for r in coverage["relations"]:
        key = (r["from"], r["type"], r["to"])
        if r["from"] not in units or r["to"] not in units or r["from"] == r["to"] or key in seen:
            raise Rejected("COVERAGE_RELATION_INVALID")
        seen.add(key)
    return units


def assess_coverage(coverage, source, gold):
    """Gold matches semantic spans, not model IDs, rule count or REVIEW outcomes.

This bounded structural oracle cannot certify free-text semantic equivalence;
unmatched/ambiguous representations require review, not guessed approval.
"""
    units = validate_coverage(coverage, source)
    mapping, checks = {}, []
    for expected in gold["units"]:
        matches = [u for u in units.values() if all(q in u["quote"] for q in expected["needles"])]
        exact = [u for u in matches if u["quote"] in expected["needles"]]
        matches = exact or matches
        errors = []
        if len(matches) != 1:
            errors.append("MISSING_OR_AMBIGUOUS_SEMANTIC_UNIT")
        else:
            actual = matches[0]
            mapping[expected["key"]] = actual["id"]
            for key in ("kind", "state", "predicate", "appliesWhen"):
                if key in expected and canonical(actual[key]) != canonical(expected[key]):
                    errors.append("SEMANTIC_" + key.upper() + "_MISMATCH")
        checks.append({"semanticKey": expected["key"], "passed": not errors, "errors": errors})
    # One broad quote cannot stand in for multiple independently linked conditions.
    if len(set(mapping.values())) != len(mapping):
        checks.append({"passed": False, "errors": ["CONFLATED_SEMANTIC_UNITS"]})
    extras = sorted(set(units) - set(mapping.values()))
    if extras:
        checks.append({"passed": False, "errors": ["UNASSESSED_UNITS"], "units": extras})
    def edge(a, t, b):
        if t == "alternative_to" and a is not None and b is not None:
            a, b = sorted((a, b))
        return a, t, b
    actual_edges = {edge(r["from"], r["type"], r["to"]) for r in coverage["relations"]}
    expected_edges = {edge(mapping.get(a), t, mapping.get(b)) for a, t, b in gold["relations"]}
    relation_errors = []
    if None in {node for a, _, b in expected_edges for node in (a, b)} or expected_edges - actual_edges:
        relation_errors.append("MISSING_SEMANTIC_RELATION")
    if actual_edges - expected_edges:
        relation_errors.append("EXTRA_OR_MISBOUND_RELATION")
    return {"evaluatorVersion": "clause-coverage-gold.v0.1", "goldDigest": digest(gold),
            "coverageDigest": digest(coverage), "checks": checks,
            "mapping": mapping, "relationErrors": relation_errors,
            "passed": all(c["passed"] for c in checks) and not relation_errors,
            "businessOwnerApproved": False}


def project(coverage, source, fields, scope):
    """Only numeric/boolean subconditions; no final business/whole-clause decision.

Direct or transitive `requires` dependencies remain fail-closed. Business-process
prerequisites stay visible but are never claimed satisfied by a numeric result.
"""
    units = validate_coverage(coverage, source)
    rules, slices = [], []
    for u in units.values():
        if u["state"] != "EXECUTABLE":
            continue
        pending, visited = [u["id"]], set()
        while pending:
            node = pending.pop()
            for r in coverage["relations"]:
                if r["from"] == node and r["type"] == "requires" and r["to"] not in visited:
                    visited.add(r["to"])
                    pending.append(r["to"])
        if u["id"] in visited:
            raise Rejected("CYCLIC_CONDITION_DEPENDENCY")
        # Even executable prerequisites are not silently assumed evaluated.
        unresolved = [units[i]["quote"] for i in sorted(visited)]
        rules.append({"id": u["id"], "title": "Independent subcondition: " + u["id"],
                      "predicate": copy.deepcopy(u["predicate"]), "appliesWhen": copy.deepcopy(u["appliesWhen"]),
                      "scope": copy.deepcopy(scope), "quotes": [u["quote"]],
                      "exceptions": [], "unresolvedQuotes": unresolved})
        slices.append({"unitId": u["id"], "resultScope": "SUBCONDITION_ONLY",
                       "requiredUnits": sorted(visited), "wholeClauseDecision": "NOT_EVALUATED"})
    ir = convert({"rules": rules}, source, fields, scope) if rules else None
    return {"coverageDigest": digest(coverage), "ir": ir, "slices": slices,
            "wholeClauseDecision": "NOT_EVALUATED", "publicationAllowed": False}
