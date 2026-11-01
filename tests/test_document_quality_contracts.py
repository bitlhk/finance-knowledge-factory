import json
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.document_quality import evaluate_retrieval, load_test_set, validate_test_set


ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "quality/financial-suitability-frozen-v0.1.json"
TUNING = ROOT / "quality/financial-suitability-tuning-v0.1.json"
CLAUSES = {f"第{number}条" for number in (
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二",
    "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十", "二十一",
    "二十二", "二十三", "二十四", "二十五", "二十六", "二十七", "二十八",
    "二十九", "三十", "三十一", "三十二", "三十三", "三十四", "三十五",
    "三十六", "三十七", "三十八", "三十九", "四十", "四十一", "四十二",
    "四十三", "四十四", "四十五", "四十六", "四十七", "四十八", "四十九")}


def test_frozen_set_has_required_distribution_and_valid_gold():
    data = load_test_set(FROZEN, CLAUSES)
    assert len(data["cases"]) == 30
    assert data["purpose"] == "FROZEN_ACCEPTANCE"


def test_tuning_set_is_separate_from_frozen_acceptance():
    tuning = load_test_set(TUNING, CLAUSES)
    frozen = load_test_set(FROZEN, CLAUSES)
    assert {case["caseId"] for case in tuning["cases"]}.isdisjoint(
        {case["caseId"] for case in frozen["cases"]})
    assert {case["question"] for case in tuning["cases"]}.isdisjoint(
        {case["question"] for case in frozen["cases"]})


def test_invalid_json_is_rejected(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"cases":[', encoding="utf-8")
    with pytest.raises(Rejected, match="QUALITY_TEST_SET_JSON_INVALID"):
        load_test_set(path)


@pytest.mark.parametrize("mutation,error", [
    ("duplicate", "QUALITY_TEST_SET_DUPLICATE"),
    ("missing-clause", "QUALITY_GOLD_CLAUSE_MISSING"),
    ("no-answer-with-gold", "QUALITY_NO_ANSWER_GOLD_INVALID"),
    ("answer-without-fact", "QUALITY_FACT_GOLD_REQUIRED"),
])
def test_semantically_invalid_gold_is_rejected(mutation, error):
    data = json.loads(FROZEN.read_text(encoding="utf-8"))
    if mutation == "duplicate":
        data["cases"][1]["question"] = data["cases"][0]["question"]
    elif mutation == "missing-clause":
        data["cases"][0]["expectedClauses"] = ["第九十九条"]
    elif mutation == "no-answer-with-gold":
        data["cases"][-1]["expectedClauses"] = ["第二条"]
    else:
        data["cases"][0]["answerFacts"] = []
    with pytest.raises(Rejected, match=error):
        validate_test_set(data, CLAUSES)


def test_retrieval_metrics_require_all_multi_evidence_and_score_no_answer():
    data = json.loads(FROZEN.read_text(encoding="utf-8"))
    rows = []
    for case in data["cases"]:
        clauses = case["expectedClauses"][:1] or ["第二条"]
        rows.append({"caseId": case["caseId"], "latencyMs": 10,
                     "candidates": [{"rank": 1, "chunkId": "chunk", "clauses": clauses,
                                     "scoreBps": 9000, "termScoreBps": 9000,
                                     "vectorScoreBps": 9000}]})
    report = evaluate_retrieval(data, rows, {"name": "test"}, "engine", "embedding")
    multi = next(case for case in report["cases"] if case["caseId"] == "confusable-record-vs-assessment-term")
    assert multi["failureClassifications"] == ["INSUFFICIENT_EVIDENCE"]
    assert report["metricsBps"]["noAnswerFalsePositive"] == 10000
