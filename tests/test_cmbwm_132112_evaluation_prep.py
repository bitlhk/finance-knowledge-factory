import pytest

from business_knowledge.cmbwm_132112 import quality_test_set
from knowledge_core.contracts import Rejected
from tools.prepare_cmbwm_132112_evaluation import (ensure_source_active,
                                                   gateway_registration_id,
                                                   selected_test_set,
                                                   source_classification_id)


SOURCE = "a" * 64


def test_smoke_selection_keeps_frozen_cases_unchanged():
    original = quality_test_set(SOURCE)
    selected = selected_test_set(SOURCE, ["cmbwm-risk",
                                           "cmbwm-fee-discount"])
    assert selected["purpose"] == "BLIND_ACCEPTANCE"
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


class SourceCore:
    def __init__(self, current=None, error="SOURCE_NOT_EFFECTIVE"):
        self.current = current
        self.error = error
        self.activations = []

    def _source_current(self, actor, source_digest, effective_from):
        if self.current is not None:
            return self.current
        raise Rejected(self.error)

    def activate_source(self, actor, source_digest, effective_from):
        self.activations.append((actor, source_digest, effective_from))
        return "b" * 64


def test_evaluation_retry_reuses_exact_active_source():
    core = SourceCore(current="c" * 64)
    assert ensure_source_active(core, "actor", SOURCE, "2026-10-30") == "c" * 64
    assert core.activations == []


def test_evaluation_first_attempt_activates_source():
    core = SourceCore()
    assert ensure_source_active(core, "actor", SOURCE, "2026-10-30") == "b" * 64
    assert core.activations == [("actor", SOURCE, "2026-10-30")]


def test_evaluation_retry_does_not_bypass_revocation():
    core = SourceCore(error="SOURCE_SUPERSEDED_OR_REVOKED")
    with pytest.raises(Rejected, match="SOURCE_SUPERSEDED_OR_REVOKED"):
        ensure_source_active(core, "actor", SOURCE, "2026-10-30")
    assert core.activations == []


def test_evaluation_retry_has_immutable_gateway_registration():
    assert gateway_registration_id("v1") != gateway_registration_id("retry2")


def test_candidate_source_has_immutable_classification_registration():
    assert source_classification_id("a" * 64).endswith("a" * 12)
    assert source_classification_id("a" * 64) != source_classification_id("b" * 64)
