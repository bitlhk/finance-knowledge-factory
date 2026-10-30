import hashlib
import json
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected
from probes.llm.archive_coverage import verify_engine
from probes.llm.candidate_bundle import evidence_digest, verify
from probes.llm.coverage import assess_coverage
from probes.llm.coverage_recipe import messages
from probes.llm.linked import decode_envelope


ROOT = Path(__file__).parents[1] / "evidence/m1-round4"


def test_frozen_batch_no_lost_attempts_or_gold_in_messages():
    frozen = json.loads((ROOT / "frozen.json").read_text())
    assert evidence_digest(frozen) == json.loads((ROOT / "freeze-receipt.json").read_text())["digest"]
    summary = json.loads((ROOT / "summary.json").read_text())
    assert [r["id"] for r in summary["attempts"]] == [a["id"] for a in frozen["attempts"]]
    assert len(summary["attempts"]) == 8
    for attempt in frozen["attempts"]:
        record = json.loads((ROOT / "attempts" / (attempt["id"] + ".json")).read_text())
        assert record["request"]["messages"] == messages(frozen["recipe"], frozen["sources"][attempt["case"]]["source"])
        assert record["requestDigest"] == evidence_digest(record["request"])
        assert record["modelCall"] == "COMPLETED"
    assert summary["cost"] is None


def test_old_and_archived_bundles_replay_without_rescoring():
    raw = (ROOT.parent / "m1-round3/sources/regulation.html").read_bytes()
    for path in [*sorted((ROOT / "attempts").glob("*-bundle.json")), *sorted((ROOT / "archive").glob("*-bundle.json"))]:
        bundle = json.loads(path.read_text())
        assert verify(raw, bundle["parts"], bundle["manifest"])
        assert not bundle["parts"]["assessment"]["passed"]


def test_engine_receipt_is_batch_specific_and_retains_failures():
    request = json.loads((ROOT / "engine-request.json").read_text())
    response = json.loads((ROOT / "archive/engine-response.json").read_text())
    rows = verify_engine(request, response)
    assert len(rows) == 30
    assert sum(r["passed"] for r in rows) == 24
    assert response["engineCalls"] == 0
    response["results"][0]["id"] = "another-run"
    with pytest.raises(Rejected):
        verify_engine(request, response)


def test_all_exported_receipts_have_fixed_hashes():
    index = json.loads((ROOT / "INDEX.json").read_text())
    for path, expected in index["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected


def test_rejected_model_response_not_repaired_into_executable_ir():
    record = json.loads((ROOT / "attempts/P43-1.json").read_text())
    assert record["errorCode"] == "EXECUTABLE_CONDITION_REQUIRED"
    coverage, _ = decode_envelope(record["response"]["choices"][0]["message"]["content"])
    frozen = json.loads((ROOT / "frozen.json").read_text())
    with pytest.raises(Rejected, match="EXECUTABLE_CONDITION_REQUIRED"):
        assess_coverage(coverage, frozen["sources"]["P43"]["source"], frozen["gold"]["P43"])
    assert not (ROOT / "attempts/P43-1-bundle.json").exists()
