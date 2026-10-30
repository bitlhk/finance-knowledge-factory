"""Offline source-body verification; never overwrite original retrieval results."""
import argparse
import hashlib
import json
from pathlib import Path

from probes.documents.anchor_bridge import build
from probes.documents.html_evidence import normalize, verify


def match_chunks(content, clauses):
    text = normalize(content)
    return [c for c in clauses if normalize(c["text"]) in text]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--source", required=True, type=Path)
    args = ap.parse_args()
    original = json.loads((args.run / "report.json").read_text())
    frozen = json.loads((args.run / "frozen.json").read_text())
    clauses = json.loads(Path("evidence/m1-round2/html-comparison.json").read_text())["results"]["docling"]["chunks"]
    raw = args.source.read_bytes()
    assert all(verify(raw, c) for c in clauses)
    source, bridge = build(raw, clauses, "native-retrieval-evidence")
    lookup = {g["id"]: g for g in frozen["questions"]}
    rows = []
    for record in original["records"]:
        gold = lookup[record["id"]]
        hits = []
        for chunk in record.get("response", {}).get("chunks", []):
            body = chunk.get("content_with_weight", chunk.get("content", ""))
            matched = match_chunks(body, clauses)
            labels = [c["clause"] for c in matched]
            hits.append({"chunkId": chunk.get("id"), "sourceClauses": labels,
                         "anchorIds": [m["anchorId"] for m in bridge["mappings"] if m["clause"] in labels],
                         "correct": gold["clause"] in labels and normalize(gold["needle"]) in normalize(body)})
        rows.append({"id": record["id"], "execution": record["execution"], "hits": hits,
                     "top1": bool(hits) and hits[0]["correct"], "top3": any(h["correct"] for h in hits[:3])})
    result = {"method": "WHOLE_SOURCE_CLAUSE_AND_FROZEN_NEEDLE", "originalReportBytesDigest": hashlib.sha256((args.run / "report.json").read_bytes()).hexdigest(),
              "source": source, "bridge": bridge, "records": rows,
              "top1": sum(r["top1"] for r in rows), "top3": sum(r["top3"] for r in rows), "total": len(rows)}
    with (args.run / "source-review.json").open("x") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2))
    print({k: result[k] for k in ("method", "top1", "top3", "total")})


if __name__ == "__main__":
    main()
