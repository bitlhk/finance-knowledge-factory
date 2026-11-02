"""Build the auditable AMSYLJ01 root-cause report from immutable evidence."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path("examples/business/customer-manager/amsylj01"))
    args = parser.parse_args()
    root = args.root
    archived = json.loads((root / "acceptance/amsylj01-real-evaluation-20261102.json").read_text())
    provenance = json.loads((root / "generated/amsylj01-provenance.json").read_text())
    review = json.loads((root / "analysis/root-cause-review-v0.1.json").read_text())
    by_case = {item["caseId"]:item for item in archived["cases"]}
    by_review = {item["caseId"]:item for item in review["cases"]}
    by_internal = {item["coreClause"]:item for item in provenance["mappings"]}
    if set(by_case) != set(by_review) or len(by_case) != 18:
        raise ValueError("ROOT_CAUSE_CASE_MISMATCH")
    cases = []
    for case_id, item in by_case.items():
        expected = []
        for internal in item["retrievalEvaluation"]["expectedClauses"]:
            mapping = by_internal[internal]
            expected.append({
                "internalUnit":internal,
                "sourcePosition":mapping["clause"],
                "originalAnchors":mapping["originalAnchors"],
            })
        cases.append({
            "caseId":case_id,
            "question":item["question"],
            "originalAnswer":item["answer"],
            "baselineClassification":item["classification"],
            "rootCauses":by_review[case_id]["rootCauses"],
            "correctOriginalEvidence":expected,
            "selectedInternalUnits":item["retrievalEvaluation"]["selectedClauses"],
            "answerCitations":item["answerCitations"],
            "factChecks":item["factChecks"],
            "citationChecks":item["citationChecks"],
            "failureStage":by_review[case_id]["failureStage"],
            "repair":by_review[case_id]["repair"],
            "verification":by_review[case_id]["verification"],
        })
    result = {
        "schemaVersion":"business-quality-root-cause-report.v0.1",
        "baselineDigest":archived["qualityAdmissionDigest"],
        "baselineDecision":archived["decision"],
        "categories":review["categories"],
        "cases":cases,
    }
    output = root / "analysis/amsylj01-18-case-root-cause-v0.1.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    counts = {key:sum(key in item["rootCauses"] for item in cases)
              for key in review["categories"]}
    lines = ["# AMSYLJ01 18题逐题根因", "",
             "本报告由冻结的原始回答、Retrieval Trace、引用、金标和原文锚点生成。",
             "原始 REJECT 不覆盖；内部‘第几条’仅作旧索引标识，不作为银行原文编号。", "",
             "## 分类统计", "",
             "| 分类 | 数量 | 含义 |", "|---|---:|---|"]
    lines += [f"| {key} | {counts[key]} | {value} |"
              for key, value in review["categories"].items()]
    lines += ["", "## 逐题结论", "",
              "| 题目 | 分类 | 基线 | 正确来源位置 | 失败环节 | 验证标准 |",
              "|---|---|---|---|---|---|"]
    for item in cases:
        sources = "；".join(value["sourcePosition"]
                           for value in item["correctOriginalEvidence"]) or "非产品文档权威"
        clean = lambda value:value.replace("|", "／").replace("\n", " ")
        lines.append("| " + " | ".join((item["caseId"],
            ",".join(item["rootCauses"]) or "通过", item["baselineClassification"],
            clean(sources), clean(item["failureStage"]), clean(item["verification"]))) + " |")
    lines += ["", "完整原始答案、原文锚点、事实检查和修复建议见同目录 JSON。", ""]
    (root / "analysis/AMSYLJ01-18-CASE-ROOT-CAUSE.md").write_text(
        "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
