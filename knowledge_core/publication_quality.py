"""Fail-closed quality admission computed from immutable evaluation objects."""
from .contracts import digest


def assess(structure, index_mapping, retrieval, answer, evidence_authority='HARNESS_ARCHIVE'):
    checks = {
        "sourceStructureComplete": structure.get("structureCoverageBps") == 10000,
        "sourceAnchorsExact": structure.get("anchorAccuracyBps") == 10000,
        "parserCoverageComplete": structure.get("parserCoverageBps") == 10000,
        "articleSequenceComplete": not structure.get("missingArticleNumbers"),
        "indexMapsAllArticles": index_mapping.get("coverageBps") == 10000,
        "retrievalExecutedByCore": retrieval.get("execution") == "CORE_EXECUTED",
        "recallAt3Complete": retrieval.get("metricsBps", {}).get("recallAt3") == 10000,
        "hitAt1AtLeast90": retrieval.get("metricsBps", {}).get("hitAt1", 0) >= 9000,
        "mrrAtLeast95": retrieval.get("metricsBps", {}).get("mrr", 0) >= 9500,
        "noAnswerFalsePositiveZero": retrieval.get("metricsBps", {}).get("noAnswerFalsePositive") == 0,
        "allRetrievalCasesPass": bool(retrieval.get("cases")) and all(
            case.get("passed") is True for case in retrieval["cases"]),
        "realHarnessAnswerEvaluation": (
            evidence_authority == "HARNESS_ARCHIVE"
            and answer.get("execution") == "CORE_CORRELATED_HARNESS_ARCHIVE"
            and isinstance(answer.get("runtimeEvidenceDigest"), str)
            and len(answer["runtimeEvidenceDigest"]) == 64
        ),
        "answerFactAccuracyComplete": answer.get("metricsBps", {}).get("factAccuracy") == 10000,
        "answerCitationAccuracyComplete": answer.get("metricsBps", {}).get("citationAccuracy") == 10000,
        "answerForbiddenClaimsAccurate": (
            answer.get("schemaVersion") not in {
                "document-answer-evaluation.v0.2", "document-answer-evaluation.v0.3"}
            or answer.get("metricsBps", {}).get("forbiddenClaimAccuracy") == 10000
        ),
        "allAnswerCasesClassified": bool(answer.get("cases")) and all(
            case.get("classification") in {"CORRECT", "CORRECT_REFUSAL"}
            for case in answer["cases"]),
    }
    if evidence_authority == "FACTORY_WORKER":
        checks["qualifiedFactoryAnswerEvaluation"] = (
            answer.get("execution") == "CORE_CORRELATED_FACTORY_WORKER"
            and isinstance(answer.get("runtimeEvidenceDigest"), str)
            and len(answer["runtimeEvidenceDigest"]) == 64
        )
        checks.pop("realHarnessAnswerEvaluation")
    result = {"schemaVersion":"document-quality-gate.v0.2" if evidence_authority == "FACTORY_WORKER"
              else "document-quality-gate.v0.1",
              "decision":"PASS" if all(checks.values()) else "REJECT", "checks":checks}
    return {**result, "digest":digest(result)}
