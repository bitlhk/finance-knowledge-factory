"""Post-experiment diagnostics v0.2.1. Never overwrite frozen v0.2 results."""
from probes.llm.coverage_review_v2 import assess


def review(output, source, gold):
    result = assess(output, source, gold)
    result["version"] = "coverage-review-addendum.v0.2.1"
    result["postObservationAnalysis"] = True
    result["notNewExperimentScore"] = True
    units = {u["id"]: u for u in output["units"]}
    branches = {a["branch"] for a in gold["atoms"] if a["branch"]}
    atoms = {a["key"]: a for a in gold["atoms"]}
    actual = {(r["from"], r["type"], r["to"]) for r in output["relations"]}
    suppressed = set()
    for a, relation, b in gold["relations"]:
        if relation != "alternative_to":
            continue
        left, right = result["mapping"].get(a), result["mapping"].get(b)
        if (right, relation, left) in actual:
            suppressed.add(a + ":" + relation + ":" + b)
            suppressed.add(right + ":" + relation + ":" + left)
    findings = []
    for item in result["findings"]:
        if item["key"] in suppressed and item["reason"] in (
                "REQUIRED_RELATION_NOT_PROVEN", "EXTRA_RELATION_REQUIRES_REVIEW"):
            continue
        item = dict(item)
        if item["reason"] == "WRONG_BRANCH_BINDING":
            provided = units[result["mapping"][item["key"]]]["branchQuote"] or ""
            other = branches - {atoms[item["key"]]["branch"]}
            if not any(branch in provided for branch in other):
                item.update(category="UNVERIFIABLE", reason="QUALIFIER_DOES_NOT_ESTABLISH_SUBJECT_BRANCH")
        findings.append(item)
    result["findings"] = findings
    result["status"] = ("SEMANTIC_ERROR" if any(f["category"] == "SEMANTIC_ERROR" for f in findings)
                        else "REVIEW_REQUIRED" if findings else "AUTOMATED_COVERAGE_MATCH")
    return result
