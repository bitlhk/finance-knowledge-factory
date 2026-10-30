import copy
import hashlib
import json
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected
from probes.llm.archive_coverage import verify_engine
from probes.llm.candidate_bundle import evidence_digest
from probes.llm.coverage_review_addendum import review
from probes.llm.lowering_bundle import seal, verify
from probes.flowable.compiler import compile_rule


ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "evidence/m1-verified-lowering"


def read(path):
    return json.loads((EVIDENCE / path).read_text())


def test_four_frozen_calls_and_old_artifacts_unchanged():
    frozen = read("frozen.json")
    assert evidence_digest(frozen) == read("freeze-receipt.json")["digest"]
    assert frozen["heldOut"] == ["P13", "P41"]
    for path, digest in frozen["implementation"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    summary = read("summary.json")
    assert [a["id"] for a in summary["attempts"]] == [a["id"] for a in frozen["attempts"]]
    assert len(summary["attempts"]) == 4
    assert all(a["modelCall"] == "COMPLETED" for a in summary["attempts"])
    for attempt in frozen["attempts"]:
        record = read("attempts/" + attempt["id"] + ".json")
        assert record["requestDigest"] == evidence_digest(record["request"])
        assert record["freezeDigest"] == read("freeze-receipt.json")["digest"]
        assert {k: record["request"][k] for k in frozen["parameters"]} == frozen["parameters"]
        assert "gold" not in record["request"]["messages"][0]["content"].lower()
    for row in read("retrospective.json")["rows"]:
        path = ROOT / "evidence/m1-round4/attempts" / (row["id"] + ".json")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sourceRecordSha256"]


def test_content_hashes_and_semantic_replay():
    for path, digest in read("INDEX.json")["files"].items():
        assert hashlib.sha256((EVIDENCE / path).read_bytes()).hexdigest() == digest
    raw = (ROOT / "evidence/m1-round3/sources/regulation.html").read_bytes()
    for path in sorted((EVIDENCE / "attempts").glob("*-bundle.json")):
        bundle = json.loads(path.read_text())
        assert verify(raw, bundle["parts"], bundle["manifest"])


@pytest.mark.parametrize("damage", ["formula", "source", "response", "recipe", "gold", "compiled"])
def test_resealing_does_not_hide_tampered_production_evidence(damage):
    bundle = read("attempts/P43-1-bundle.json")
    p = bundle["parts"]
    if damage == "formula":
        p["projection"]["ir"]["rules"][0]["predicate"]["right"] = {"literal": {"type": "integer", "value": 0}}
    elif damage == "source":
        p["source"]["content"] += "x"
    elif damage == "response":
        p["coverage"]["units"][0]["state"] = "PROPOSED_NUMERIC"
    elif damage == "recipe":
        p["recipe"]["revision"] = 100
    elif damage == "gold":
        p["gold"]["atoms"] = []
    else:
        p["compiled"] = []
    raw = (ROOT / "evidence/m1-round3/sources/regulation.html").read_bytes()
    with pytest.raises(Rejected):
        verify(raw, p, seal(raw, p))


def test_governed_candidate_and_numeric_proof_not_conflated():
    governed = verify_engine(read("engine-request.json"), read("archive/engine-response.json"))
    numeric = verify_engine(read("addendum/engine-request.json"), read("addendum/archive/engine-response.json"))
    assert len(governed) == 10 and sum(r["passed"] for r in governed) == 4
    assert read("archive/engine-response.json")["engineCalls"] == 0
    assert len(numeric) == 10 and all(r["passed"] for r in numeric)
    assert read("addendum/archive/engine-response.json")["engineCalls"] == 5
    assert not {r["id"] for r in numeric} & {r["id"] for r in governed}
    bundle = read("attempts/P43-1-bundle.json")
    proof = read("addendum/numeric-proofs.json")["proofs"][0]
    assert proof["originalBundleDigest"] == evidence_digest(bundle)
    assert proof["originalGovernedProjectionDigest"] == evidence_digest(bundle["parts"]["projection"])
    assert proof["originalDependenciesUnchanged"]
    assert proof["wholeClauseDecision"] == "REVIEW_REQUIRED" and not proof["publicationAllowed"]
    assert bundle["parts"]["projection"]["ir"]["rules"][0]["unresolved"]
    assert proof["compiled"] == compile_rule(proof["ir"], "numeric-proof")
    assert proof["compiled"]["compiledDigest"] != bundle["parts"]["compiled"][0]["compiledDigest"]


def test_qualifier_is_not_misreported_as_explicit_wrong_subject():
    bundle = read("attempts/P08-1-bundle.json")["parts"]
    original = bundle["assessment"]
    assert original["status"] == "SEMANTIC_ERROR"
    revised = review(bundle["coverage"], bundle["source"], bundle["gold"])
    assert revised["status"] == "REVIEW_REQUIRED"
    assert revised["postObservationAnalysis"] and revised["notNewExperimentScore"]
    wrong = copy.deepcopy(bundle["coverage"])
    next(u for u in wrong["units"] if "现金流" in u["quote"])["branchQuote"] = "用于个人消费"
    assert review(wrong, bundle["source"], bundle["gold"])["status"] == "SEMANTIC_ERROR"


def test_reverse_symmetric_edge_does_not_establish_other_missing_relations():
    p = read("attempts/P43-1-bundle.json")["parts"]
    result = review(p["coverage"], p["source"], p["gold"])
    assert result["status"] == "REVIEW_REQUIRED"
    assert not any(":alternative_to:" in f["key"] for f in result["findings"])
    assert any(f["reason"] == "MERGED_UNIT_RELATION_NOT_PROVEN" for f in result["findings"])


def test_engine_receipts_link_to_exact_request_and_snapshot():
    request = read("engine-request.json")
    response = read("archive/engine-response.json")
    receipt = read("archive/receipt.json")
    assert receipt["requestDigest"] == evidence_digest(request)
    assert receipt["responseDigest"] == evidence_digest(response)
    for attempt in read("frozen.json")["attempts"]:
        name = attempt["id"] + "-bundle.json"
        snapshot, final = read("attempts/" + name), read("archive/" + name)
        assert final["parentSnapshotDigest"] == evidence_digest(snapshot)
        assert final["engineRunId"] == receipt["engineRunId"]
        assert final["cases"] == snapshot["parts"]["execution"]["cases"]
        assert {r["id"] for r in final["results"]} == {c["id"] for c in final["cases"]}
