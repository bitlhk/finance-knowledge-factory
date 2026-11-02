"""Export the immutable AMSYLJ01 business-quality closeout evidence."""
import argparse
import json
from pathlib import Path
import sqlite3


PASSING_CLASSIFICATIONS = {"CORRECT", "CORRECT_REFUSAL"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--preparation-task", type=Path, required=True)
    parser.add_argument("--execution-task", type=Path, required=True)
    parser.add_argument("--runtime-evidence", required=True)
    parser.add_argument("--answer-evaluation", required=True)
    parser.add_argument("--quality-admission", required=True)
    parser.add_argument("--failed-model-receipt", action="append", default=[])
    parser.add_argument("--worker-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    database = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)

    def get(digest, kind):
        row = database.execute(
            "select kind,body from objects where digest=?", (digest,)
        ).fetchone()
        if not row or row[0] != kind:
            raise ValueError("ACCEPTANCE_OBJECT_MISSING:" + kind)
        return json.loads(row[1])

    preparation = json.loads(args.preparation_task.read_text(encoding="utf-8"))
    execution = json.loads(args.execution_task.read_text(encoding="utf-8"))
    runtime = get(
        args.runtime_evidence, "document-factory-evaluation-runtime-evidence"
    )
    answer = get(args.answer_evaluation, "document-answer-evaluation")
    admission = get(args.quality_admission, "document-quality-admission")

    if runtime["assignmentDigest"] != execution["assignmentDigest"]:
        raise ValueError("ACCEPTANCE_ASSIGNMENT_MISMATCH")
    if runtime["leaseDigest"] != execution["leaseDigest"]:
        raise ValueError("ACCEPTANCE_LEASE_MISMATCH")
    if admission["decision"] != "REJECT":
        raise ValueError("CLOSEOUT_EXPECTED_REJECT")

    runtime_by_id = {item["caseId"]: item for item in runtime["cases"]}
    answer_by_id = {item["caseId"]: item for item in answer["cases"]}
    retrieval_by_id = {
        item["caseId"]: item for item in preparation["retrievalReport"]["cases"]
    }
    case_ids = execution["caseIds"]
    expected = set(case_ids)
    if expected != set(runtime_by_id) or expected != set(answer_by_id):
        raise ValueError("ACCEPTANCE_CASE_MISMATCH")
    if expected != set(retrieval_by_id):
        raise ValueError("ACCEPTANCE_RETRIEVAL_CASE_MISMATCH")

    cases = []
    for case_id in case_ids:
        raw = runtime_by_id[case_id]
        evaluated = answer_by_id[case_id]
        cases.append(
            {
                "caseId": case_id,
                "question": retrieval_by_id[case_id]["question"],
                "classification": evaluated["classification"],
                "originalAnswer": raw["answer"],
                "answerDigest": raw["answerDigest"],
                "retrievalEvaluation": retrieval_by_id[case_id],
                "retrievedEvidence": raw["retrievedEvidence"],
                "answerCitations": raw["answerCitations"],
                "factChecks": evaluated["factChecks"],
                "citationChecks": evaluated["citationChecks"],
                "forbiddenClaimChecks": evaluated["forbiddenClaimChecks"],
                "requestId": raw["requestId"],
                "traceId": raw["traceId"],
                "candidateReceiptDigest": raw["candidateReceiptDigest"],
                "modelReceiptDigest": raw["modelReceiptDigest"],
            }
        )

    failed_receipts = []
    for digest in args.failed_model_receipt:
        receipt = get(digest, "model-invocation-receipt")
        failed_receipts.append(
            {
                "digest": digest,
                "caseId": receipt["caseId"],
                "outcome": receipt["outcome"],
                "requestId": receipt["requestId"],
                "traceId": receipt["traceId"],
                "provider": receipt["provider"],
                "modelRef": receipt["modelRef"],
                "assignmentDigest": receipt["assignmentDigest"],
            }
        )

    result = {
        "schemaVersion": "amsylj01-business-quality-closeout.v0.3",
        "decision": admission["decision"],
        "publicationResult": "NOT_ATTEMPTED_QUALITY_REJECTED",
        "approvalDigest": None,
        "manifestDigest": None,
        "code": {"workerSha": args.worker_sha},
        "candidateDigest": preparation["candidateDigest"],
        "sourceDigest": preparation["sourceDigest"],
        "indexDigest": preparation["indexDigest"],
        "profileDigest": preparation["profileDigest"],
        "testSetDigest": preparation["testSetDigest"],
        "retrievalEvaluationDigest": preparation["retrievalDigest"],
        "assignmentDigest": execution["assignmentDigest"],
        "leaseDigest": execution["leaseDigest"],
        "runtimeEvidenceDigest": args.runtime_evidence,
        "answerEvaluationDigest": args.answer_evaluation,
        "qualityAdmissionDigest": args.quality_admission,
        "modelIdentity": runtime["modelIdentity"],
        "verification": runtime["verification"],
        "retrievalMetricsBps": preparation["retrievalReport"]["metricsBps"],
        "answerMetricsBps": answer["metricsBps"],
        "qualityChecks": admission["checks"],
        "retrievalProfile": preparation["retrievalReport"]["profile"],
        "retrievalLatencyMs": preparation["retrievalReport"]["latencyMs"],
        "retainedFailedModelReceipts": failed_receipts,
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    passed = [
        item["caseId"]
        for item in cases
        if item["classification"] in PASSING_CLASSIFICATIONS
    ]
    answer_failures = [
        item["caseId"]
        for item in cases
        if item["classification"] not in PASSING_CLASSIFICATIONS
    ]
    retrieval_failures = [
        item["caseId"]
        for item in cases
        if not item["retrievalEvaluation"]["passed"]
    ]
    retrieval = result["retrievalMetricsBps"]
    answer_metrics = result["answerMetricsBps"]
    lines = [
        "# AMSYLJ01 业务质量收口验收",
        "",
        "结论：**REJECT，不审批、不发布、不生成 Manifest**。",
        "",
        "## 真实隔离运行",
        "",
        f"- 真实 OpenJiuwen + DeepSeek 完成：{len(cases)} 题。",
        f"- Core 验证类型：`{runtime['verification']}`。",
        f"- 自动评价正确或正确拒答：{len(passed)}/{len(cases)}。",
        f"- 自动评价失败：{len(answer_failures)}/{len(cases)}（{', '.join(answer_failures)}）。",
        f"- 检索门禁失败：{len(retrieval_failures)}/{len(cases)}（{', '.join(retrieval_failures)}）。",
        f"- 保留真实模型失败回执：{len(failed_receipts)} 份；最终成功运行未覆盖失败记录。",
        "",
        "## 指标",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| Recall@3 | {retrieval['recallAt3']/100:.2f}% |",
        f"| Hit@1 | {retrieval['hitAt1']/100:.2f}% |",
        f"| MRR | {retrieval['mrr']/100:.2f}% |",
        f"| 无答案误报 | {retrieval['noAnswerFalsePositive']/100:.2f}% |",
        f"| 自动事实准确 | {answer_metrics['factAccuracy']/100:.2f}% |",
        f"| 自动引用准确 | {answer_metrics['citationAccuracy']/100:.2f}% |",
        f"| 禁止性结论 | {answer_metrics['forbiddenClaimAccuracy']/100:.2f}% |",
        "",
        "自动指标不替代独立业务复核；业务复核及同口径 Before/After 见 `analysis/BUSINESS-QUALITY-CLOSEOUT.md`。",
        "",
        "原始回答、引用证据、来源位置、requestId、traceId、模型回执和 Core 检查见同名 JSON。",
        "",
    ]
    args.output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
