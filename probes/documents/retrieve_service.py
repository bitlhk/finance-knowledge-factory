"""Frozen questions against actual RAGFlow HTTP retrieval; preserve every response."""
import json
from pathlib import Path
import re
import time
import uuid

from knowledge_core.contracts import digest
from probes.documents.ragflow_client import Client, STATE


def main():
    client = Client()
    dataset = json.loads((STATE / "dataset.json").read_text())["id"]
    document = json.loads((STATE / "documents.json").read_text())[0]["id"]
    gold = json.loads(Path("probes/documents/retrieval-gold.json").read_text())
    out = Path(".m1-local/retrieval") / uuid.uuid4().hex
    out.mkdir(parents=True)
    parameters = {"dataset_ids": [dataset], "document_ids": [document], "page": 1, "page_size": 3,
                  "knn_top_k": 64, "knn_num_candidates": 128, "rerank_candidates_count": 64,
                  "similarity_threshold": 0, "keywords_similarity_weight": 0.7,
                  "include_knowledge_compilation": False, "highlight": False}
    (out / "frozen.json").write_text(json.dumps({"goldDigest": digest(gold), "questions": gold,
             "parameters": parameters, "model": "BAAI/bge-small-zh-v1.5", "reranker": None,
             "mode": "RAGFLOW_HTTP_NATIVE_HYBRID", "independentBlindTest": False}, ensure_ascii=False, indent=2))
    chunks = client.call("GET", f"/datasets/{dataset}/documents/{document}/chunks?page_size=100")
    (out / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=2))
    records = []
    for case in gold:
        started = time.monotonic()
        record = {"id": case["id"], "expected": case["clause"]}
        try:
            response = client.call("POST", "/retrieval", json={**parameters, "question": case["question"]})
            labels = [re.findall(r"第[一二三四五六七八九十百零〇0-9]+条", c.get("content_with_weight", c.get("content", ""))) for c in response.get("chunks", [])]
            record.update(execution="COMPLETED", response=response, clauseLabels=labels,
                          top1Correct=bool(labels) and case["clause"] in labels[0],
                          top3Correct=any(case["clause"] in group for group in labels[:3]))
        except Exception as exc:
            record.update(execution="FAILED", error=str(exc))
        record["elapsedSeconds"] = round(time.monotonic() - started, 3)
        (out / (case["id"] + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2))
        records.append(record)
    report = {"mode": "RAGFLOW_HTTP_NATIVE_HYBRID", "goldDigest": digest(gold), "records": records,
              "completed": sum(r["execution"] == "COMPLETED" for r in records), "total": len(gold),
              "top1": sum(r.get("top1Correct", False) for r in records),
              "top3": sum(r.get("top3Correct", False) for r in records)}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print({k: v for k, v in report.items() if k != "records"})
    print("Evidence:", out)


if __name__ == "__main__":
    main()
