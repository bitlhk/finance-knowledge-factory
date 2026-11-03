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
    clients = []
    monkeypatch.setattr(service_process, "_json", lambda _: {
        "tenant":"tenant-a",
        "actors":{
            "host":{"principal":"host", "authority":"host-authority"},
            "worker":{"principal":"worker", "authority":"worker-authority"},
            "gateway":{"principal":"gateway", "authority":"gateway-authority"},
        },
        "serviceCredentials":{
            role:{"uid":position + 1000, "tokenDigest":"a" * 64}
            for position, role in enumerate(("host", "worker", "gateway"))},
        "workerTokenFile":"unused", "coreSocket":"core.sock",
        "gatewaySocket":"gateway.sock", "caseIds":["case-1"]})
    monkeypatch.setattr(service_process, "_load_task", lambda config, path: {
        "caseIds":["case-1"], "pythonVersion":"3.12",
        "openJiuwenVersion":"0.1.17.post1"})
    monkeypatch.setattr(service_process, "managed_runtime_versions",
                        lambda:("3.12", "0.1.17.post1"))
    monkeypatch.setattr(service_process, "_token", lambda _: "x" * 64)
    class ReadyClient:
        def __init__(self, *args):
            self.ready = False
            clients.append(self)

        def wait_until_ready(self):
            self.ready = True

    monkeypatch.setattr(service_process, "UnixEvaluationClient", ReadyClient)
    monkeypatch.setattr(service_process, "CandidateEvaluationWorker", FakeWorker)
    return clients


def test_worker_writes_group_readable_host_handoff(monkeypatch, tmp_path):
    clients = configure_worker(monkeypatch)
    handoff = tmp_path / "handoff"
    handoff.mkdir(mode=0o750)
    output = handoff / "runs.json"
    service_process.run_worker(SimpleNamespace(
        config="unused", task="task.json", output=output))
    assert output.stat().st_mode & 0o777 == 0o640
    assert '"caseId": "case-1"' in output.read_text(encoding="utf-8")
    assert len(clients) == 2 and all(client.ready for client in clients)


def test_worker_rejects_uncontrolled_handoff_directory(monkeypatch, tmp_path):
    configure_worker(monkeypatch)
    handoff = tmp_path / "handoff"
    handoff.mkdir(mode=0o757)
    with pytest.raises(ValueError, match="HANDOFF_DIRECTORY_INVALID"):
        service_process.run_worker(SimpleNamespace(
            config="unused", task="task.json", output=handoff / "runs.json"))
