"""Append final engine receipts without rewriting execution-time snapshots."""
import argparse
import hashlib
import json
from pathlib import Path

from knowledge_core.contracts import Rejected
from probes.llm.candidate_bundle import evidence_digest, seal, verify
from probes.llm.run_coverage import RAW_PATH, write


def verify_engine(request, response):
    expected = {c["id"]: c for c in request["cases"]}
    rows = response.get("results", [])
    if len(expected) != len(request["cases"]) or len(rows) != len(expected) or {r["id"] for r in rows} != set(expected):
        raise Rejected("ENGINE_RECEIPT_CASE_MISMATCH")
    if response.get("engine") != "org.flowable:flowable-dmn-engine:8.0.0":
        raise Rejected("ENGINE_RECEIPT_VERSION_MISMATCH")
    for row in rows:
        case = expected[row["id"]]
        if row["expected"] != case["expected"] or row["passed"] != (row["actual"] == case["expected"]):
            raise Rejected("ENGINE_RECEIPT_RESULT_MISMATCH")
        if "guard" in case and (row["actual"] != case["guard"] or row["executor"] != "INPUT_SCOPE_GUARD"):
            raise Rejected("ENGINE_RECEIPT_GUARD_MISMATCH")
    return rows


def archive(output, engine_dir):
    request = json.loads((output / "engine-request.json").read_text())
    actual_request = json.loads((engine_dir / "request.json").read_text())
    if request != actual_request:
        raise Rejected("ENGINE_REQUEST_NOT_THIS_BATCH")
    response = json.loads((engine_dir / "response.json").read_text())
    rows = verify_engine(request, response)
    destination = output / "archive"
    destination.mkdir(exist_ok=False)
    write(destination / "engine-response.json", response)
    write(destination / "engine-exit.json", json.loads((engine_dir / "exit.json").read_text()))
    write(destination / "engine-receipt.json", {
        "requestDigest": evidence_digest(request), "responseDigest": evidence_digest(response),
        "engineRunId": engine_dir.name, "buildLogSha256": hashlib.sha256((engine_dir / "build.log").read_bytes()).hexdigest(),
        "engineCalls": response["engineCalls"], "publicationAllowed": False})
    raw = RAW_PATH.read_bytes()
    for path in sorted((output / "attempts").glob("*-bundle.json")):
        old = json.loads(path.read_text())
        verify(raw, old["parts"], old["manifest"])
        attempt_id = path.name.removesuffix("-bundle.json")
        parts = old["parts"]
        own = [r for r in rows if r["id"].startswith(attempt_id + "-")]
        own_request = [c for c in request["cases"] if c["id"].startswith(attempt_id + "-")]
        for case in own_request:
            if case["compiledDigest"] not in {m["compiledDigest"] for m in parts["compiled"]}:
                raise Rejected("ENGINE_COMPILED_IDENTITY_MISMATCH")
        parts["execution"] = {"status": "FINAL_RECEIPT" if own else "NOT_EXECUTABLE_OR_UNMATCHED",
                              "parentSnapshotDigest": evidence_digest(old), "engineRunId": engine_dir.name,
                              "batchRequestDigest": evidence_digest(request), "batchResponseDigest": evidence_digest(response),
                              "cases": own_request, "results": own, "publicationAllowed": False}
        manifest = seal(raw, parts)
        verify(raw, parts, manifest)
        write(destination / path.name, {"manifest": manifest, "parts": parts})
    index = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(output.rglob("*.json")) if p.name != "INDEX.json"}
    write(output / "INDEX.json", {"schemaVersion": "m1-evidence-index.v0.1", "files": index,
                                  "publicationAllowed": False, "cost": None})
    print("Archived:", len(index), "files; engineCalls:", response["engineCalls"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("engine_dir", type=Path)
    args = parser.parse_args()
    archive(args.output, args.engine_dir)
