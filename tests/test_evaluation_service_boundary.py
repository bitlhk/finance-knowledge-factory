import asyncio
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from evaluation_worker import (CandidateEvaluationWorker,
    EvaluationCoreBoundary, EvaluationGatewayBoundary,
    IpcCandidateQueryClient, IpcGatewayClient,
    IpcModelAuthorizationClient, ServiceCredentials, UnixEvaluationClient,
    UnixEvaluationServer, require_distinct_service_users, token_digest)
from knowledge_core.contracts import Rejected
from knowledge_core.documents import DocumentCore
from tests.test_factory_evaluation_worker import (DEPLOYMENT, FUTURE, GATEWAY,
    MANAGER, WORKER, prepare)


TOKENS = {role:(role + "-credential-") * 3
          for role in ("host", "worker", "gateway")}


def credentials(**uids):
    return ServiceCredentials({role:{"uid":uids.get(role, os.getuid()),
        "tokenDigest":token_digest(TOKENS[role])} for role in TOKENS})


def test_production_service_users_must_be_distinct():
    require_distinct_service_users({"host":1001, "worker":1002,
                                    "gateway":1003})
    with pytest.raises(ValueError, match="SERVICE_IDENTITY_NOT_ISOLATED"):
        require_distinct_service_users({"host":1001, "worker":1001,
                                        "gateway":1003})


def test_credentials_bind_both_role_token_and_peer_uid():
    registry = credentials(host=1001, worker=1002, gateway=1003)
    assert registry.authorize(1002, "worker", TOKENS["worker"]) == "worker"
    for uid, role, token in ((1001, "worker", TOKENS["worker"]),
                             (1002, "host", TOKENS["worker"]),
                             (1002, "worker", TOKENS["host"]),
                             (1002, "worker", "short")):
        with pytest.raises(Rejected, match="EVALUATION_SERVICE_UNAUTHORIZED"):
            registry.authorize(uid, role, token)


class FakeCore:
    def __init__(self):
        self.calls = []

    def _called(self, name, actor, *args):
        self.calls.append((name, actor, args))
        return {"name":name} if name not in {"runtime", "answer", "admission"} else name

    def query_document_candidate_for_evaluation(self, actor, *args):
        return self._called("query", actor, *args)

    def authorize_model_egress(self, actor, *args):
        return self._called("authorize", actor, *args)

    def prepare_model_invocation(self, actor, *args):
        return self._called("prepare", actor, *args)

    def record_model_invocation(self, actor, *args):
        return self._called("record", actor, *args)

    def register_factory_evaluation_runtime_evidence(self, actor, *args):
        return self._called("runtime", actor, *args)

    def register_answer_evaluation(self, actor, *args):
        return self._called("answer", actor, *args)

    def assess_document_quality(self, actor, *args):
        return self._called("admission", actor, *args)

    def close(self):
        pass


def core_boundary():
    core = FakeCore()
    boundary = EvaluationCoreBoundary(lambda:core, "worker-actor", "host-actor",
        "gateway-actor", lambda:"evidence-client", assignment_digest="assignment",
        lease_digest="lease", gateway_registration_digest="registration",
        gateway_deployment_id="deployment", purpose="quality",
        redaction_profile="source-only",
        authorization_expires_at="2030-01-01T00:00:00+00:00",
        candidate_digest="candidate", profile_digest="profile",
        test_set_digest="tests", retrieval_digest="retrieval",
        worker_build_digest="worker-build", python_version="3.12",
        openjiuwen_version="0.1.17.post1",
        gateway_runtime_identity={"id":"gateway"})
    return core, boundary


def test_core_boundary_owns_actors_and_has_no_publish_operation():
    core, boundary = core_boundary()
    boundary.dispatch("worker", "candidate.query", {
        "caseId":"case-1", "requestId":"request-1", "traceId":"trace-1"})
    boundary.dispatch("worker", "model.authorize", {
        "candidateReceiptDigest":"receipt", "authorizationId":"auth-1"})
    boundary.dispatch("gateway", "model.prepare", {
        "authorizationDigest":"auth", "requestId":"request-2",
        "traceId":"trace-2"})
    boundary.dispatch("host", "evaluation.finalize", {"runs":[]})
    assert [(name, actor) for name, actor, _ in core.calls] == [
        ("query", "worker-actor"), ("authorize", "host-actor"),
        ("prepare", "gateway-actor"), ("runtime", "host-actor"),
        ("answer", "host-actor"), ("admission", "host-actor")]
    assert all("publish" not in operation for operation in boundary.OPERATIONS)
    with pytest.raises(Rejected, match="EVALUATION_SERVICE_OPERATION_FORBIDDEN"):
        boundary.dispatch("worker", "evaluation.finalize", {"runs":[]})
    with pytest.raises(Rejected, match="EVALUATION_SERVICE_OPERATION_FORBIDDEN"):
        boundary.dispatch("host", "publish", {})


class EchoBoundary:
    def dispatch(self, role, operation, payload):
        if role != "worker" or operation != "echo":
            raise Rejected("EVALUATION_SERVICE_OPERATION_FORBIDDEN")
        return {"payload":payload}


def running_server(tmp_path, boundary):
    server = UnixEvaluationServer(tmp_path / "service.sock", credentials(), boundary,
                                  enforce_distinct_users=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_server_defaults_to_requiring_os_identity_isolation(tmp_path):
    with pytest.raises(ValueError, match="SERVICE_IDENTITY_NOT_ISOLATED"):
        UnixEvaluationServer(tmp_path / "service.sock", credentials(),
                             EchoBoundary())


def test_server_replaces_only_a_stale_unix_socket(tmp_path):
    path = tmp_path / "service.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path)); stale.close()
    server = UnixEvaluationServer(path, credentials(), EchoBoundary(),
                                  enforce_distinct_users=False)
    server.server_close()
    path.write_text("not a socket", encoding="utf-8")
    with pytest.raises(FileExistsError, match="SERVICE_SOCKET_EXISTS"):
        UnixEvaluationServer(path, credentials(), EchoBoundary(),
                             enforce_distinct_users=False)


def test_server_does_not_replace_an_active_unix_socket(tmp_path):
    server, thread = running_server(tmp_path, EchoBoundary())
    try:
        with pytest.raises(FileExistsError, match="SERVICE_SOCKET_EXISTS"):
            UnixEvaluationServer(server.path, credentials(), EchoBoundary(),
                                 enforce_distinct_users=False)
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_unix_service_uses_peer_credentials_and_does_not_echo_secrets(tmp_path):
    server, thread = running_server(tmp_path, EchoBoundary())
    try:
        client = UnixEvaluationClient(server.path, "worker", TOKENS["worker"])
        assert client.call("echo", {"value":7}) == {"payload":{"value":7}}
        bad = UnixEvaluationClient(server.path, "worker", TOKENS["host"])
        with pytest.raises(Rejected, match="EVALUATION_SERVICE_UNAUTHORIZED"):
            bad.call("echo", {"value":7})
        wrong_role = UnixEvaluationClient(server.path, "host", TOKENS["host"])
        with pytest.raises(Rejected, match="EVALUATION_SERVICE_OPERATION_FORBIDDEN"):
            wrong_role.call("echo", {"value":7})
    finally:
        server.shutdown(); server.server_close(); thread.join()
    assert not server.path.exists()


class WorkerCoreBoundary:
    def dispatch(self, role, operation, payload):
        assert role == "worker"
        if operation == "candidate.query":
            return {"receiptDigest":"candidate-" + payload["caseId"]}
        if operation == "model.authorize":
            return "authorization-" + payload["candidateReceiptDigest"]
        raise Rejected("EVALUATION_SERVICE_OPERATION_FORBIDDEN")


class WorkerGatewayBoundary:
    def dispatch(self, role, operation, payload):
        assert role == "worker" and operation == "model.invoke"
        return "model-receipt-" + payload["authorizationDigest"]


def test_worker_runs_through_ipc_without_core_or_gateway_objects(tmp_path):
    core_server, core_thread = running_server(tmp_path / "core", WorkerCoreBoundary())
    gateway_server, gateway_thread = running_server(
        tmp_path / "gateway", WorkerGatewayBoundary())
    try:
        core_client = UnixEvaluationClient(
            core_server.path, "worker", TOKENS["worker"])
        gateway_client = UnixEvaluationClient(
            gateway_server.path, "worker", TOKENS["worker"])
        worker = CandidateEvaluationWorker(
            IpcCandidateQueryClient(core_client),
            IpcModelAuthorizationClient(core_client),
            IpcGatewayClient(gateway_client))
        result = asyncio.run(worker.run(["case-1"]))
        assert result[0]["candidateReceiptDigest"] == "candidate-case-1"
        assert result[0]["modelReceiptDigest"].startswith("model-receipt-")
    finally:
        core_server.shutdown(); core_server.server_close(); core_thread.join()
        gateway_server.shutdown(); gateway_server.server_close(); gateway_thread.join()


def test_real_document_core_uses_one_sqlite_connection_per_ipc_request(tmp_path):
    initial, evidence, values = prepare(tmp_path)
    database = tmp_path / "core.db"
    initial.close()
    boundary = EvaluationCoreBoundary(
        lambda:DocumentCore(database), WORKER, MANAGER, GATEWAY,
        lambda:evidence,
        assignment_digest=values["assignment"], lease_digest=values["lease"],
        gateway_registration_digest=values["gateway"],
        gateway_deployment_id=DEPLOYMENT.id, purpose="answer-quality",
        redaction_profile="source-only", authorization_expires_at=FUTURE,
        candidate_digest=values["candidateDigest"],
        profile_digest=values["profile"], test_set_digest=values["tests"],
        retrieval_digest=values["retrieval"], worker_build_digest="a" * 64,
        python_version="3.12", openjiuwen_version="0.1.17.post1",
        gateway_runtime_identity={"unused":"in-this-test"})
    server, thread = running_server(tmp_path / "real-core", boundary)
    client = UnixEvaluationClient(server.path, "worker", TOKENS["worker"])

    def query(suffix):
        try:
            return ("ok", client.call("candidate.query", {
                "caseId":"quality-service-hours",
                "requestId":"concurrent-request-" + suffix,
                "traceId":"concurrent-trace-" + suffix}))
        except Rejected as error:
            return ("rejected", error.code)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(query, ("one", "two")))
    finally:
        server.shutdown(); server.server_close(); thread.join()
    assert [result[0] for result in results].count("ok") == 1, results
    assert ("rejected", "EVALUATION_LEASE_REPLAYED") in results
    check = DocumentCore(database)
    try:
        count = check.db.execute(
            "SELECT count(*) FROM objects WHERE kind=? AND "
            "json_extract(body,'$.leaseDigest')=?",
            ("document-candidate-query-receipt", values["lease"])).fetchone()[0]
        assert count == 1
        assert check.db.execute("pragma integrity_check").fetchone()[0] == "ok"
    finally:
        check.close()


class AsyncGateway:
    def __init__(self):
        self.loops = []

    async def invoke(self, authorization, request_id, trace_id):
        self.loops.append(id(asyncio.get_running_loop()))
        return {"authorization":authorization, "requestId":request_id,
                "traceId":trace_id}


def test_gateway_boundary_accepts_only_worker_invoke():
    gateway = AsyncGateway()
    boundary = EvaluationGatewayBoundary(gateway)
    try:
        result = boundary.dispatch("worker", "model.invoke", {
            "authorizationDigest":"authorization", "requestId":"request",
            "traceId":"trace"})
        assert result["authorization"] == "authorization"
        with pytest.raises(Rejected, match="EVALUATION_SERVICE_OPERATION_FORBIDDEN"):
            boundary.dispatch("host", "model.invoke", {
                "authorizationDigest":"authorization", "requestId":"request",
                "traceId":"trace"})
    finally:
        boundary.close()


def test_gateway_reuses_one_event_loop_for_six_sequential_calls():
    gateway = AsyncGateway()
    boundary = EvaluationGatewayBoundary(gateway)
    try:
        for position in range(6):
            boundary.dispatch("worker", "model.invoke", {
                "authorizationDigest":f"authorization-{position}",
                "requestId":f"request-{position}",
                "traceId":f"trace-{position}"})
    finally:
        boundary.close()
    assert len(gateway.loops) == 6
    assert len(set(gateway.loops)) == 1
