import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation_worker import service_process


class FakeWorker:
    def __init__(self, *args):
        pass

    async def run(self, case_ids):
        await asyncio.sleep(0)
        return [{"caseId":case_ids[0], "candidateReceiptDigest":"a" * 64,
                 "modelReceiptDigest":"b" * 64}]


def configure_worker(monkeypatch):
    monkeypatch.setattr(service_process, "_json", lambda _: {
        "workerTokenFile":"unused", "coreSocket":"core.sock",
        "gatewaySocket":"gateway.sock", "caseIds":["case-1"]})
    monkeypatch.setattr(service_process, "_token", lambda _: "x" * 64)
    monkeypatch.setattr(service_process, "UnixEvaluationClient",
                        lambda *args: object())
    monkeypatch.setattr(service_process, "CandidateEvaluationWorker", FakeWorker)


def test_worker_writes_group_readable_host_handoff(monkeypatch, tmp_path):
    configure_worker(monkeypatch)
    handoff = tmp_path / "handoff"
    handoff.mkdir(mode=0o750)
    output = handoff / "runs.json"
    service_process.run_worker(SimpleNamespace(config="unused", output=output))
    assert output.stat().st_mode & 0o777 == 0o640
    assert '"caseId": "case-1"' in output.read_text(encoding="utf-8")


def test_worker_rejects_uncontrolled_handoff_directory(monkeypatch, tmp_path):
    configure_worker(monkeypatch)
    handoff = tmp_path / "handoff"
    handoff.mkdir(mode=0o757)
    with pytest.raises(ValueError, match="HANDOFF_DIRECTORY_INVALID"):
        service_process.run_worker(SimpleNamespace(
            config="unused", output=handoff / "runs.json"))
