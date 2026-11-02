import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_first_business_product_is_single_bank_and_source_pinned():
    register = load("examples/business/customer-manager/boc-amsylj01-source-register.json")
    assert register["institution"] == "中国银行股份有限公司"
    assert register["productId"] == "boc-wealth-service-amsylj01"
    assert len(register["sources"]) == 3
    assert {source["role"] for source in register["sources"]} == {
        "PRODUCT_TERMS", "SALES_AGREEMENT", "SUITABILITY_AND_CUSTOMER_RIGHTS"}
    assert all(source["url"].startswith(("https://www.boc.cn/",
                                         "https://pic.bankofchina.com/"))
               for source in register["sources"])
    assert all(len(source["sha256"]) == 64 for source in register["sources"])
    assert register["excludedSources"][0]["sourceId"].startswith("icbc-")


def test_customer_manager_set_covers_task_answers_and_live_fact_boundaries():
    suite = load("examples/business/customer-manager/boc-wealth-manager-test-set-v0.1.json")
    assert suite["institution"] == "中国银行股份有限公司"
    assert len(suite["cases"]) == 18
    assert len({case["caseId"] for case in suite["cases"]}) == 18
    assert {"DIRECT", "EXCEPTION", "NO_ANSWER", "VERSION", "PROHIBITION"}.issubset(
        {case["category"] for case in suite["cases"]})
    live = [case for case in suite["cases"] if case.get("requiredLiveFacts")]
    assert len(live) >= 6
    no_answers = [case for case in suite["cases"] if case["category"] == "NO_ANSWER"]
    assert len(no_answers) == 3
    assert all(case.get("requiredBehavior") and case["forbiddenClaims"]
               for case in no_answers)


def test_loan_review_is_separate_preparation_not_wealth_product_input():
    suite = load("examples/business/loan-review/boc-business-loan-review-test-set-draft-v0.1.json")
    assert suite["status"] == "PREPARATION_ONLY_NOT_PR14_ACCEPTANCE"
    assert suite["institution"] == "中国银行股份有限公司"
    assert len(suite["cases"]) == 15
    cross_bank = next(case for case in suite["cases"] if case["caseId"] == "lr-015-cross-bank")
    assert "Reject cross-bank rule substitution" in cross_bank["requiredBehavior"]
