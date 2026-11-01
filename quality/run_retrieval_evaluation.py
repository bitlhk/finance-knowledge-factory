"""Run an explicit read-only retrieval profile against a pinned document index."""
import argparse
import json
from pathlib import Path
import sqlite3
import time

from knowledge_core.document_quality import evaluate_retrieval, load_test_set
from m2.ragflow import Ragflow
from knowledge_core.retrieval_quality import trace_select
from quality.retrieval_profiles import PROFILES


def _record(item, clauses_by_chunk, *, stage, decision, reasons):
    return {"stage": stage, "rank": item["rank"], "chunkId": item["id"],
            "clauses": clauses_by_chunk.get(item["id"], []),
            "scoreBps": item["scoreBps"], "termScoreBps": item["termScoreBps"],
            "vectorScoreBps": item["vectorScoreBps"],
            "postRankScoreBps": item.get("postRankScoreBps"),
            "decision": decision, "reasons": reasons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--index-digest", required=True)
    parser.add_argument("--test-set", type=Path, required=True)
    parser.add_argument("--private-config", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="baseline")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    row = database.execute("select body from objects where digest=? and kind='document-index'",
                           (args.index_digest,)).fetchone()
    if row is None:
        parser.error("Pinned document index not found")
    document_index = json.loads(row[0])
    clauses_by_chunk = {chunk["id"]: chunk["clauses"] for chunk in document_index["index"]["chunks"]}
    available = {clause["clause"] for clause in document_index["clauses"]}
    test_set = load_test_set(args.test_set, available)
    client = Ragflow(args.private_config / "local-credentials.json",
                     args.private_config / "http-setup.json")
    experiment = PROFILES[args.profile]
    rows = []
    for case in test_set["cases"]:
        started = time.monotonic()
        trace = trace_select(client, document_index["index"]["datasetId"],
                             document_index["index"]["documentId"], case["question"], experiment)
        raw_candidates, ranked_candidates = trace["retrieved"], trace["ranked"]
        final_candidates = trace["selected"]
        filtering = [_record(item, clauses_by_chunk, stage="FILTERED",
            decision=item["qualityDecision"], reasons=item["qualityReasons"])
            for item in trace["filtered"]]
        rows.append({"caseId": case["caseId"], "latencyMs": round((time.monotonic() - started) * 1000),
                     "stages": {
                         "retrieved": [_record(item, clauses_by_chunk, stage="RETRIEVED",
                             decision="CANDIDATE", reasons=["returned by pinned RAGFlow profile"])
                             for item in raw_candidates],
                         "ranked": [_record(item, clauses_by_chunk, stage="RANKED",
                             decision="CANDIDATE", reasons=["ordered by pinned post-ranker"])
                             for item in ranked_candidates],
                         "filtered": filtering,
                         "selected": [_record(item, clauses_by_chunk, stage="SELECTED",
                             decision="SELECT", reasons=["within first three supported candidates"])
                             for item in final_candidates],
                     },
                     "queryVariants": trace["queryVariants"],
                     "candidates": [_record(item, clauses_by_chunk, stage="SELECTED",
                         decision="SELECT", reasons=["within first three supported candidates"])
                         for item in final_candidates]})
    report = evaluate_retrieval(test_set, rows, {"name": args.profile, **experiment},
                                document_index["index"]["engineIdentity"],
                                document_index["index"]["embeddingIdentity"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
