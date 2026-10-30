"""Same-byte parser comparison + shared lexical retrieval diagnostic, NOT RAGFlow search."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import uuid

from rank_bm25 import BM25Okapi
from .html_evidence import locate, verify


def tokens(s):
    s = "".join(re.findall(r"[\u4e00-\u9fff0-9a-zA-Z]", s)).lower()
    return [s[i:i + 2] for i in range(len(s) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--docling", required=True)
    ap.add_argument("--ragflow", required=True)
    args = ap.parse_args()
    raw = Path(args.source).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    docling = json.loads(Path(args.docling).read_text())
    ragflow = json.loads(Path(args.ragflow).read_text())
    assert ragflow["sourceDigest"] == sha
    texts = {"docling": [x["text"] for x in docling["texts"]], "ragflow": [x.get("text", "") for x in ragflow["items"]]}
    gold_path = Path(__file__).with_name("retrieval-gold.json")
    gold = json.loads(gold_path.read_text())
    report = {"sourceDigest": sha, "goldDigest": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
              "retrieval": "SHARED_BM25_BIGRAM_DIAGNOSTIC_NOT_RAGFLOW_SERVICE",
              "bm25": {"package": "rank-bm25==0.2.2", "k1": 1.5, "b": 0.75, "epsilon": 0.25},
              "independentBlindTest": False, "results": {}}
    for name, values in texts.items():
        chunks = locate(raw, values)
        assert all(verify(raw, c) for c in chunks)
        assert len({c["clause"] for c in chunks}) == len(chunks)
        engine = BM25Okapi([tokens(c["text"]) for c in chunks])
        results = []
        for case in gold:
            exact = [c for c in chunks if c["clause"] == case["clause"]]
            assert len(exact) == 1 and case["needle"] in exact[0]["text"], "Frozen gold mismatch: " + case["id"]
            scores = engine.get_scores(tokens(case["question"]))
            indexes = sorted(range(len(chunks)), key=lambda i: (-scores[i], chunks[i]["clause"]))[:3]
            hits = [chunks[i]["clause"] for i in indexes]
            results.append({"id": case["id"], "top3": hits, "expected": case["clause"],
                            "top1Correct": hits[0] == case["clause"], "top3Correct": case["clause"] in hits})
        report["results"][name] = {"rawItems": len(values), "nativeAnchorAvailable": False,
            "locatedClauses": len(chunks), "verifiedAnchors": sum(len(c["anchors"]) for c in chunks),
            "top1": sum(c["top1Correct"] for c in results), "top3": sum(c["top3Correct"] for c in results),
            "total": len(gold), "queries": results, "chunks": chunks}
    out = Path(".m1-local/comparison") / uuid.uuid4().hex
    out.mkdir(parents=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("Evidence:", out)
    print(json.dumps({name: {k:v for k,v in r.items() if k not in ("queries", "chunks")} for name,r in report["results"].items()},ensure_ascii=False))


if __name__ == "__main__":
    main()
