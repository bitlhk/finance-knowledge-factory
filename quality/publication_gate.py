"""Fail-closed internal admission for newly produced HTML document products."""
from knowledge_core.contracts import digest


def assess(structure, index_mapping, retrieval, answer):
    checks = {
        "sourceStructureComplete": structure.get("structureCoverageBps") == 10000,
        "sourceAnchorsExact": structure.get("anchorAccuracyBps") == 10000,
        "parserCoverageComplete": structure.get("parserCoverageBps") == 10000,
        "articleSequenceComplete": not structure.get("missingArticleNumbers"),
        "indexMapsAllArticles": index_mapping.get("coverageBps") == 10000,
        "recallAt3Complete": retrieval.get("metricsBps", {}).get("recallAt3") == 10000,
        "hitAt1AtLeast90": retrieval.get("metricsBps", {}).get("hitAt1", 0) >= 9000,
        "mrrAtLeast95": retrieval.get("metricsBps", {}).get("mrr", 0) >= 9500,
        "noAnswerFalsePositiveZero": retrieval.get("metricsBps", {}).get("noAnswerFalsePositive") == 0,
        "allRetrievalCasesPass": bool(retrieval.get("cases")) and all(
            case.get("passed") is True for case in retrieval["cases"]),
        "realHarnessAnswerEvaluation": answer.get("execution") == "REAL_HARNESS_DEEPSEEK",
        "answerFactAccuracyComplete": answer.get("metricsBps", {}).get("factAccuracy") == 10000,
        "answerCitationAccuracyComplete": answer.get("metricsBps", {}).get("citationAccuracy") == 10000,
        "allAnswerCasesClassified": bool(answer.get("cases")) and all(
            case.get("classification") in {
                "CORRECT", "RETRIEVAL_MISS", "INSUFFICIENT_EVIDENCE",
                "ANSWER_FACT_ERROR", "ANSWER_CITATION_ERROR", "CORRECT_REFUSAL"}
            for case in answer["cases"]),
    }
    result = {"schemaVersion": "document-quality-gate.v0.1",
              "decision": "PASS" if all(checks.values()) else "REJECT",
              "checks": checks}
    return {**result, "digest": digest(result)}
