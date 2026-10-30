"""Conservative atomic-coverage checks; differences never become automatic passes."""
from knowledge_core.contracts import digest
from probes.llm.coverage_gold_v2 import VERSION
from probes.llm.semantic_v2 import validate


def assess(output, source, gold):
    units = validate(output, source)
    findings, mapping = [], {}
    def issue(category, key, reason):
        findings.append({"category": category, "key": key, "reason": reason})
    for atom in gold["atoms"]:
        hits = [u for u in units.values() if atom["needle"] in u["quote"]]
        exact = [u for u in hits if u["quote"].rstrip("。") == atom["needle"]]
        hits = exact or hits
        if len(hits) != 1:
            issue("UNVERIFIABLE", atom["key"], "MISSING_OR_AMBIGUOUS_ATOMIC_EVIDENCE")
            continue
        u = hits[0]
        mapping[atom["key"]] = u["id"]
        if atom["branch"]:
            if u["branchQuote"] is None:
                issue("UNVERIFIABLE", atom["key"], "BRANCH_NOT_EXPLICIT")
            elif atom["branch"] not in u["branchQuote"]:
                issue("SEMANTIC_ERROR", atom["key"], "WRONG_BRANCH_BINDING")
        if u["kind"] != atom["kind"]:
            issue("REPRESENTATION_DIFFERENCE", atom["key"], "KIND_REQUIRES_REVIEW")
        if atom["kind"] in ("PRECONDITION", "FOLLOW_UP", "REFERENCE") and u["state"] == "PROPOSED_NUMERIC":
            issue("SEMANTIC_ERROR", atom["key"], "PROCESS_OR_REFERENCE_IS_NOT_NUMERIC")
        if atom.get("forbidNumeric") and u["state"] == "PROPOSED_NUMERIC":
            issue("SEMANTIC_ERROR", atom["key"], "UNSUPPORTED_SEMANTICS_PROPOSED_AS_NUMERIC")
    used = set(mapping.values())
    for key in sorted(set(units) - used):
        issue("UNVERIFIABLE", key, "ADDITIONAL_SOURCE_SUPPORTED_UNIT_REQUIRES_REVIEW")
    actual = {(r["from"], r["type"], r["to"]) for r in output["relations"]}
    consumed = set()
    for a, kind, b in gold["relations"]:
        left, right = mapping.get(a), mapping.get(b)
        key = a + ":" + kind + ":" + b
        if left is None or right is None:
            issue("UNVERIFIABLE", key, "RELATION_ENDPOINT_NOT_VERIFIED")
        elif left == right:
            supported = any(e["edge"] == [a, kind, b] and e["quote"] in units[left]["quote"]
                            for e in gold["embeddedRelations"])
            if not supported:
                issue("UNVERIFIABLE", key, "MERGED_UNIT_RELATION_NOT_PROVEN")
        elif (left, kind, right) in actual:
            consumed.add((left, kind, right))
        else:
            variants = {e for e in actual if e[0] == left and e[2] == right}
            if variants:
                issue("REPRESENTATION_DIFFERENCE", key, "RELATION_TYPE_REQUIRES_REVIEW")
                consumed.update(variants)
            else:
                issue("UNVERIFIABLE", key, "REQUIRED_RELATION_NOT_PROVEN")
    for edge in sorted(actual - consumed):
        issue("UNVERIFIABLE", ":".join(edge), "EXTRA_RELATION_REQUIRES_REVIEW")
    categories = {f["category"] for f in findings}
    status = ("SEMANTIC_ERROR" if "SEMANTIC_ERROR" in categories else
              "REVIEW_REQUIRED" if findings else "AUTOMATED_COVERAGE_MATCH")
    return {"version": VERSION, "goldDigest": digest(gold), "semanticDigest": digest(output),
            "status": status, "findings": findings, "mapping": mapping,
            "atomicEvidenceCount": len(mapping), "expectedAtomicCount": len(gold["atoms"]),
            "businessOwnerApproved": False, "publicationAllowed": False}
