import pytest

from business_knowledge.cmbwm_132112 import quality_test_set
from tools.prepare_cmbwm_132112_evaluation import selected_test_set


SOURCE = "a" * 64


def test_smoke_selection_keeps_frozen_cases_unchanged():
    original = quality_test_set(SOURCE)
    selected = selected_test_set(SOURCE, ["cmbwm-risk",
                                           "cmbwm-fee-discount"])
    assert selected["purpose"] == "SMOKE_ACCEPTANCE"
    assert [case["caseId"] for case in selected["cases"]] == [
        "cmbwm-risk", "cmbwm-fee-discount"]
    assert selected["cases"] == [case for case in original["cases"]
                                  if case["caseId"] in {
                                      "cmbwm-risk",
                                      "cmbwm-fee-discount"}]


@pytest.mark.parametrize("case_ids", [
    ["missing-case"],
    ["cmbwm-risk", "cmbwm-risk"],
])
def test_smoke_selection_rejects_unknown_or_duplicate_cases(case_ids):
    with pytest.raises(ValueError, match="QUALITY_SMOKE_CASE_INVALID"):
        selected_test_set(SOURCE, case_ids)
