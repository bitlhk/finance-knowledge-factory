"""One bounded real-service ingestion, recording failures as well as successes."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import uuid

from probes.documents.ragflow_client import Client, STATE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--retrieval-fixture", action="store_true",
                    help="Select a completed ingestion for the subsequent fixed 30-question probe")
    args = ap.parse_args()
    raw = args.source.read_bytes()
    if len(raw) > 20_000_000:
        raise SystemExit("SOURCE_TOO_LARGE")
    out = Path(".m1-local/ingestion") / uuid.uuid4().hex
    out.mkdir(parents=True)
    report = {"sourceDigest": hashlib.sha256(raw).hexdigest(), "name": args.source.name,
              "bytes": len(raw), "execution": "STARTED", "originalPageNumbersVerified": False}
    client = Client()
    configured = json.loads((STATE / "http-setup.json").read_text())["models"]
    matching = [m["model_id"] for m in configured if m["name"] == "BAAI/bge-small-zh-v1.5"]
    if len(matching) != 1:
        raise SystemExit("EMBEDDING_MODEL_AMBIGUOUS_OR_ABSENT")
    model = matching[0]
    try:
        dataset = client.call("POST", "/datasets", json={"name": "m1-format-" + out.name,
                   "embedding_model": model, "parse_type": 1, "parser_id": "laws"})
        report["dataset"] = dataset
        docs = client.call("POST", f"/datasets/{dataset['id']}/documents",
                           files={"file": (args.source.name, raw)})
        report["documents"] = docs
        ids = [d["id"] for d in docs]
        report["parseReceipt"] = client.call("POST", f"/datasets/{dataset['id']}/chunks", json={"document_ids": ids})
        end = time.monotonic() + 240
        while time.monotonic() < end:
            state = client.call("GET", f"/datasets/{dataset['id']}/documents")
            report["state"] = state
            rows = state.get("docs", state.get("documents", []))
            if rows and all(d.get("progress") == 1 or d.get("progress", 0) < 0 for d in rows):
                report["execution"] = "COMPLETED" if all(d.get("progress") == 1 for d in rows) else "PARSE_FAILED"
                break
            time.sleep(2)
        else:
            report["execution"] = "TIMEOUT"
        if report["execution"] == "COMPLETED":
            report["chunks"] = client.call("GET", f"/datasets/{dataset['id']}/documents/{ids[0]}/chunks?page_size=100")
            if args.retrieval_fixture:
                for name, value in [("dataset.json", dataset), ("documents.json", docs), ("parse-status.json", report["state"])]:
                    (STATE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))
    except Exception as exc:
        report.update(execution="FAILED", error=str(exc))
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(report["execution"], "Evidence:", out)


if __name__ == "__main__":
    main()
