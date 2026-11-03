"""Export the immutable AMSYLJ01 v0.2 acceptance evidence and comparison."""
import argparse
import json
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--runtime-evidence", required=True)
    parser.add_argument("--answer-evaluation", required=True)
    parser.add_argument("--quality-admission", required=True)
    parser.add_argument("--worker-sha", required=True)
    parser.add_argument("--evaluator-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()

    database = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    def get(digest, kind):
        row = database.execute("select kind,body from objects where digest=?",
                               (digest,)).fetchone()
        if not row or row[0] != kind:
            raise ValueError("ACCEPTANCE_OBJECT_MISSING:" + kind)
        return json.loads(row[1])

    task = json.loads(args.task.read_text(encoding="utf-8"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    runtime = get(args.runtime_evidence,
                  "document-factory-evaluation-runtime-evidence")
    answer = get(args.answer_evaluation, "document-answer-evaluation")
    admission = get(args.quality_admission, "document-quality-admission")
    runtime_by_id = {item["caseId"]:item for item in runtime["cases"]}
    answer_by_id = {item["caseId"]:item for item in answer["cases"]}
    retrieval_by_id = {item["caseId"]:item
                       for item in task["retrievalReport"]["cases"]}
    case_ids = task["caseIds"]
    if set(case_ids) != set(runtime_by_id) or set(case_ids) != set(answer_by_id):
        raise ValueError("ACCEPTANCE_CASE_MISMATCH")
    cases = []
    for case_id in case_ids:
        evaluated = answer_by_id[case_id]
        raw = runtime_by_id[case_id]
        cases.append({
            "caseId":case_id,
            "question":retrieval_by_id[case_id]["question"],
            "classification":evaluated["classification"],
            "originalAnswer":raw["answer"],
            "answerDigest":raw["answerDigest"],
            "retrievalEvaluation":retrieval_by_id[case_id],
            "retrievedEvidence":raw["retrievedEvidence"],
            "answerCitations":raw["answerCitations"],
            "factChecks":evaluated["factChecks"],
            "citationChecks":evaluated["citationChecks"],
            "forbiddenClaimChecks":evaluated["forbiddenClaimChecks"],
            "requestId":raw["requestId"], "traceId":raw["traceId"],
            "candidateReceiptDigest":raw["candidateReceiptDigest"],
            "modelReceiptDigest":raw["modelReceiptDigest"],
        })
    result = {
        "schemaVersion":"amsylj01-business-quality-acceptance.v0.2",
        "decision":admission["decision"],
        "publicationResult":"NOT_ATTEMPTED_QUALITY_REJECTED",
        "manifestDigest":None,
        "code":{"workerSha":args.worker_sha,
                "evaluatorSha":args.evaluator_sha},
        "lineage":{"baselineAdmissionDigest":baseline["qualityAdmissionDigest"],
                   "baselineDecision":baseline["decision"],
                   "baselineCaseCount":len(baseline["cases"])},
        "candidateDigest":task["candidateDigest"],
        "sourceDigest":task["sourceDigest"],
        "indexDigest":task["indexDigest"],
        "profileDigest":task["profileDigest"],
        "testSetDigest":task["testSetDigest"],
        "retrievalEvaluationDigest":task["retrievalDigest"],
        "assignmentDigest":task["assignmentDigest"],
        "leaseDigest":task["leaseDigest"],
        "runtimeEvidenceDigest":args.runtime_evidence,
        "answerEvaluationDigest":args.answer_evaluation,
        "qualityAdmissionDigest":args.quality_admission,
        "modelIdentity":runtime["modelIdentity"],
        "verification":runtime["verification"],
        "baselineMetrics":{"retrieval":baseline["retrievalMetricsBps"],
                           "answer":baseline["answerMetricsBps"]},
        "improvedMetrics":{"retrieval":task["retrievalReport"]["metricsBps"],
                           "answer":answer["metricsBps"]},
        "qualityChecks":admission["checks"],
        "retrievalProfile":task["retrievalReport"]["profile"],
        "retrievalLatencyMs":task["retrievalReport"]["latencyMs"],
        "cases":cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    passed = [item["caseId"] for item in cases
              if item["classification"] in {"CORRECT", "CORRECT_REFUSAL"}]
    retrieval_failures = [item["caseId"] for item in cases
                          if not item["retrievalEvaluation"]["passed"]]
    before_r, after_r = result["baselineMetrics"]["retrieval"], result["improvedMetrics"]["retrieval"]
    before_a, after_a = result["baselineMetrics"]["answer"], result["improvedMetrics"]["answer"]
    lines = ["# AMSYLJ01 业务质量改进验收", "",
        "结论：**REJECT，不发布 Manifest**。工程指标改善不等于业务发布合格。", "",
        "## Before / After", "",
        "| 指标 | 原18题基线 | v0.2（17原题+4盲测） |", "|---|---:|---:|",
        f"| Recall@3 | {before_r['recallAt3']/100:.2f}% | {after_r['recallAt3']/100:.2f}% |",
        f"| Hit@1 | {before_r['hitAt1']/100:.2f}% | {after_r['hitAt1']/100:.2f}% |",
        f"| MRR | {before_r['mrr']/100:.2f}% | {after_r['mrr']/100:.2f}% |",
        f"| 无答案误报 | {before_r['noAnswerFalsePositive']/100:.2f}% | {after_r['noAnswerFalsePositive']/100:.2f}% |",
        f"| 事实准确 | {before_a['factAccuracy']/100:.2f}% | {after_a['factAccuracy']/100:.2f}% |",
        f"| 引用准确 | {before_a['citationAccuracy']/100:.2f}% | {after_a['citationAccuracy']/100:.2f}% |",
        f"| 禁止性结论 | {before_a['forbiddenClaimAccuracy']/100:.2f}% | {after_a['forbiddenClaimAccuracy']/100:.2f}% |",
        "", "## 结果", "",
        f"- 正确回答或正确拒答：{len(passed)}/{len(cases)}（{', '.join(passed)}）。",
        f"- 检索仍失败：{len(retrieval_failures)}/{len(cases)}（{', '.join(retrieval_failures)}）。",
        "- 原始答案、原文引用、来源位置、requestId、traceId 和模型回执摘要见同名 JSON。",
        "- 原 v0.1 REJECT、原18题和原索引未覆盖；本次没有审批、发布或 Manifest。", ""]
    args.output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
