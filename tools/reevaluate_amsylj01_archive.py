"""Re-evaluate immutable archived answers with the current deterministic evaluator."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge_core.documents import _answer_references, _evaluate_answer_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--business-review", type=Path)
    args = parser.parse_args()
    raw = args.archive.read_bytes()
    archive = json.loads(raw)
    cases, passed_facts, facts = [], 0, 0
    passed_citations, citations = 0, 0
    passed_forbidden, forbidden = 0, 0
    for archived in archive["cases"]:
        retrieval = archived["retrievalEvaluation"]
        answer_citations, unmatched = _answer_references(
            archived["originalAnswer"], archived["retrievedEvidence"])
        evaluated = _evaluate_answer_case({
            "caseId":archived["caseId"],
            "expectedClauses":retrieval["expectedClauses"],
            "answerFacts":retrieval["answerFacts"],
            "forbiddenClaims":retrieval["forbiddenClaims"],
        }, {
            "answer":archived["originalAnswer"],
            "retrievedEvidence":archived["retrievedEvidence"],
            "answerCitations":answer_citations,
            "unmatchedAnswerCitations":unmatched,
        })
        passed_facts += sum(item["passed"] for item in evaluated["factChecks"])
        facts += len(evaluated["factChecks"])
        passed_citations += sum(item["passed"] for item in evaluated["citationChecks"])
        citations += len(evaluated["citationChecks"])
        passed_forbidden += sum(item["passed"] for item in evaluated["forbiddenClaimChecks"])
        forbidden += len(evaluated["forbiddenClaimChecks"])
        cases.append({
            "caseId":archived["caseId"],
            "answerDigest":archived["answerDigest"],
            "priorClassification":archived["classification"],
            "classification":evaluated["classification"],
            "factChecks":evaluated["factChecks"],
            "citationChecks":evaluated["citationChecks"],
            "forbiddenClaimChecks":evaluated["forbiddenClaimChecks"],
        })
    prior_metrics = archive.get("improvedMetrics", {}).get("answer")
    if prior_metrics is None:
        prior_metrics = archive["answerMetricsBps"]
    result = {
        "schemaVersion":"amsylj01-archived-answer-reevaluation.v0.1",
        "archiveSha256":hashlib.sha256(raw).hexdigest(),
        "archiveDecision":archive["decision"],
        "runtimeEvidenceDigest":archive["runtimeEvidenceDigest"],
        "modelIdentity":archive["modelIdentity"],
        "priorMetricsBps":prior_metrics,
        "metricsBps":{
            "factAccuracy":10000 * passed_facts // facts if facts else 10000,
            "citationAccuracy":10000 * passed_citations // citations if citations else 10000,
            "forbiddenClaimAccuracy":10000 * passed_forbidden // forbidden if forbidden else 10000,
        },
        "cases":cases,
    }
    if args.business_review:
        review = json.loads(args.business_review.read_text(encoding="utf-8"))
        reviewed = {item["caseId"]: item["businessCorrect"]
                    for item in review["cases"]}
        if set(reviewed) != {item["caseId"] for item in cases}:
            raise ValueError("BUSINESS_REVIEW_CASE_MISMATCH")
        false_negative = false_positive = true_positive = true_negative = 0
        for item in cases:
            automatic = item["classification"] in {"CORRECT", "CORRECT_REFUSAL"}
            business = reviewed[item["caseId"]]
            if automatic and business:
                true_positive += 1
            elif automatic:
                false_positive += 1
            elif business:
                false_negative += 1
            else:
                true_negative += 1
        result["businessReview"] = {
            "reviewSha256":hashlib.sha256(
                args.business_review.read_bytes()).hexdigest(),
            "truePositive":true_positive,
            "falsePositive":false_positive,
            "falseNegative":false_negative,
            "trueNegative":true_negative,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()
