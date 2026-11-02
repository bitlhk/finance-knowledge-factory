"""Authenticated local IPC boundaries for Factory evaluation services.

The transport deliberately exposes no publication, policy-management, database,
or credential-reading operation. Production launchers must additionally isolate
the three processes with distinct operating-system users.
"""
import asyncio
import hashlib
import hmac
import json
import os
import socket
import socketserver
import struct
import threading
from pathlib import Path
import re

from knowledge_core.contracts import Rejected


MAX_MESSAGE_BYTES = 1_048_576
ROLES = frozenset({"host", "worker", "gateway"})
_SHA256 = re.compile(r"[a-f0-9]{64}")


def token_digest(token):
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("SERVICE_CREDENTIAL_INVALID")
    return hashlib.sha256(token.encode()).hexdigest()


def require_distinct_service_users(role_uids):
    if set(role_uids) != ROLES or any(type(value) is not int or value < 1
                                     for value in role_uids.values()):
        raise ValueError("SERVICE_IDENTITY_INVALID")
    if len(set(role_uids.values())) != len(role_uids):
        raise ValueError("SERVICE_IDENTITY_NOT_ISOLATED")


class ServiceCredentials:
    """Server-owned role, peer UID, and token-digest registry."""

    def __init__(self, records):
        if set(records) != ROLES:
            raise ValueError("SERVICE_IDENTITY_INVALID")
        self._records = {}
        for role, record in records.items():
            if (set(record) != {"uid", "tokenDigest"}
                    or type(record["uid"]) is not int or record["uid"] < 1
                    or not isinstance(record["tokenDigest"], str)
                    or not _SHA256.fullmatch(record["tokenDigest"])):
                raise ValueError("SERVICE_IDENTITY_INVALID")
            self._records[role] = dict(record)

    def authorize(self, peer_uid, role, token):
        record = self._records.get(role)
        try:
            supplied = token_digest(token)
        except ValueError:
            raise Rejected("EVALUATION_SERVICE_UNAUTHORIZED") from None
        if (not record or peer_uid != record["uid"]
                or not hmac.compare_digest(supplied, record["tokenDigest"])):
            raise Rejected("EVALUATION_SERVICE_UNAUTHORIZED")
        return role

    @property
    def role_uids(self):
        return {role:record["uid"] for role, record in self._records.items()}


class EvaluationCoreBoundary:
    """Narrow Core facade with server-owned actors and frozen task bindings."""

    OPERATIONS = {
        "candidate.query":"worker",
        "model.authorize":"worker",
        "model.prepare":"gateway",
        "model.record":"gateway",
        "evaluation.finalize":"host",
    }

    def __init__(self, core_factory, worker_actor, host_actor, gateway_actor,
                 evidence_client_factory, *, assignment_digest, lease_digest,
                 gateway_registration_digest, gateway_deployment_id,
                 purpose, redaction_profile, authorization_expires_at,
                 candidate_digest, profile_digest, test_set_digest,
                 retrieval_digest, worker_build_digest, python_version,
                 openjiuwen_version, gateway_runtime_identity):
        self._core_factory = core_factory
        self._worker = worker_actor
        self._host = host_actor
        self._gateway = gateway_actor
        self._evidence_factory = evidence_client_factory
        self._assignment = assignment_digest
        self._lease = lease_digest
        self._gateway_registration = gateway_registration_digest
        self._deployment = gateway_deployment_id
        self._purpose = purpose
        self._redaction = redaction_profile
        self._authorization_expiry = authorization_expires_at
        self._candidate = candidate_digest
        self._profile = profile_digest
        self._test_set = test_set_digest
        self._retrieval = retrieval_digest
        self._worker_build = worker_build_digest
        self._python = python_version
        self._openjiuwen = openjiuwen_version
        self._runtime_identity = gateway_runtime_identity

    def dispatch(self, role, operation, payload):
        if self.OPERATIONS.get(operation) != role or not isinstance(payload, dict):
            raise Rejected("EVALUATION_SERVICE_OPERATION_FORBIDDEN")
        core = self._core_factory()
        try:
            if operation == "candidate.query":
                if set(payload) != {"caseId", "requestId", "traceId"}:
                    raise Rejected("EVALUATION_SERVICE_REQUEST_INVALID")
                evidence = self._evidence_factory()
                try:
                    return core.query_document_candidate_for_evaluation(
                        self._worker, self._assignment, self._lease,
                        payload["caseId"], payload["requestId"],
                        payload["traceId"], evidence)
                finally:
                    close = getattr(evidence, "close", None)
                    if close:
                        close()
            if operation == "model.authorize":
                if set(payload) != {"candidateReceiptDigest", "authorizationId"}:
                    raise Rejected("EVALUATION_SERVICE_REQUEST_INVALID")
                return core.authorize_model_egress(
                    self._host, payload["authorizationId"], 1,
                    self._assignment, payload["candidateReceiptDigest"],
                    self._gateway_registration, self._deployment, self._purpose,
                    self._redaction, self._authorization_expiry)
            if operation == "model.prepare":
                if set(payload) != {"authorizationDigest", "requestId", "traceId"}:
                    raise Rejected("EVALUATION_SERVICE_REQUEST_INVALID")
                return core.prepare_model_invocation(
                    self._gateway, self._gateway_registration,
                    payload["authorizationDigest"], payload["requestId"],
                    payload["traceId"], self._runtime_identity)
            if operation == "model.record":
                expected = {"authorizationDigest", "attemptDigest", "startedAt",
                            "endedAt", "outcome", "response",
                            "providerRequestRef", "usage"}
                if set(payload) != expected:
                    raise Rejected("EVALUATION_SERVICE_REQUEST_INVALID")
                return core.record_model_invocation(
                    self._gateway, self._gateway_registration,
                    payload["authorizationDigest"], payload["attemptDigest"],
                    payload["startedAt"], payload["endedAt"], payload["outcome"],
                    payload["response"], payload["providerRequestRef"],
                    payload["usage"])
            if set(payload) != {"runs"} or not isinstance(payload["runs"], list):
                raise Rejected("EVALUATION_SERVICE_REQUEST_INVALID")
            runtime = core.register_factory_evaluation_runtime_evidence(
                self._host, self._assignment, self._lease, self._worker_build,
                self._python, self._openjiuwen, payload["runs"])
            answer = core.register_answer_evaluation(
                self._host, self._candidate, self._profile, self._test_set,
                self._retrieval, runtime)
            admission = core.assess_document_quality(
                self._host, self._candidate, self._profile, self._test_set,
                self._retrieval, answer)
            return {"runtimeEvidenceDigest":runtime,
                    "answerEvaluationDigest":answer,
                    "qualityAdmissionDigest":admission}
        finally:
            core.close()


class PersistentAsyncRunner:
    """One event loop owned by the Gateway process for all model calls."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever,
                                        name="evaluation-gateway-loop", daemon=True)
        self._thread.start()

    def run(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    def close(self):
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()


class EvaluationGatewayBoundary:
    """Model gateway facade. Only a Worker may request a prepared invocation."""

    def __init__(self, gateway, runner=None):
        self._gateway = gateway
        self._runner = runner or PersistentAsyncRunner()

    def dispatch(self, role, operation, payload):
        if role != "worker" or operation != "model.invoke" or set(payload) != {
                "authorizationDigest", "requestId", "traceId"}:
            raise Rejected("EVALUATION_SERVICE_OPERATION_FORBIDDEN")
        return self._runner.run(self._gateway.invoke(
            payload["authorizationDigest"], payload["requestId"],
            payload["traceId"]))

    def close(self):
        self._runner.close()


class _UnixHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
            if not raw or len(raw) > MAX_MESSAGE_BYTES or not raw.endswith(b"\n"):
                raise Rejected("EVALUATION_SERVICE_REQUEST_INVALID")
            request = json.loads(raw)
            if set(request) != {"role", "token", "operation", "payload"}:
                raise Rejected("EVALUATION_SERVICE_REQUEST_INVALID")
            peer_uid = struct.unpack("3i", self.request.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))[1]
            role = self.server.credentials.authorize(
                peer_uid, request["role"], request["token"])
            result = self.server.boundary.dispatch(
                role, request["operation"], request["payload"])
            response = {"ok":True, "result":result}
        except Rejected as error:
            response = {"ok":False, "error":error.code}
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            response = {"ok":False, "error":"EVALUATION_SERVICE_REQUEST_INVALID"}
        body = json.dumps(response, ensure_ascii=False,
                          separators=(",", ":")).encode() + b"\n"
        self.wfile.write(body)


class UnixEvaluationServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path, credentials, boundary, mode=0o660,
                 *, enforce_distinct_users=True):
        if enforce_distinct_users:
            require_distinct_service_users(credentials.role_uids)
        self.path = Path(path)
        if self.path.exists():
            raise FileExistsError("EVALUATION_SERVICE_SOCKET_EXISTS")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.credentials = credentials
        self.boundary = boundary
        super().__init__(str(self.path), _UnixHandler)
        os.chmod(self.path, mode)

    def server_close(self):
        super().server_close()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class UnixEvaluationClient:
    def __init__(self, path, role, token, timeout=130):
        self.path, self.role, self.token = str(path), role, token
        self.timeout = timeout

    def call(self, operation, payload):
        request = json.dumps({"role":self.role, "token":self.token,
            "operation":operation, "payload":payload}, ensure_ascii=False,
            separators=(",", ":")).encode() + b"\n"
        if len(request) > MAX_MESSAGE_BYTES:
            raise Rejected("EVALUATION_SERVICE_REQUEST_INVALID")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(self.timeout)
            client.connect(self.path)
            client.sendall(request)
            response = b""
            while not response.endswith(b"\n"):
                chunk = client.recv(min(65536, MAX_MESSAGE_BYTES + 1 - len(response)))
                if not chunk:
                    break
                response += chunk
                if len(response) > MAX_MESSAGE_BYTES:
                    raise Rejected("EVALUATION_SERVICE_RESPONSE_INVALID")
        try:
            decoded = json.loads(response)
        except (ValueError, UnicodeError):
            raise Rejected("EVALUATION_SERVICE_RESPONSE_INVALID") from None
        if not isinstance(decoded, dict):
            raise Rejected("EVALUATION_SERVICE_RESPONSE_INVALID")
        if decoded.get("ok") is not True:
            raise Rejected(decoded.get("error", "EVALUATION_SERVICE_FAILED"))
        if set(decoded) != {"ok", "result"}:
            raise Rejected("EVALUATION_SERVICE_RESPONSE_INVALID")
        return decoded["result"]


class IpcCandidateQueryClient:
    def __init__(self, client):
        self._client = client

    def query(self, case_id, request_id, trace_id):
        return self._client.call("candidate.query", {
            "caseId":case_id, "requestId":request_id, "traceId":trace_id})


class IpcModelAuthorizationClient:
    def __init__(self, client):
        self._client = client

    def authorize(self, candidate_receipt):
        return self._client.call("model.authorize", {
            "candidateReceiptDigest":candidate_receipt["receiptDigest"],
            "authorizationId":"model-egress-" + os.urandom(16).hex()})


class IpcGatewayClient:
    def __init__(self, client):
        self._client = client

    async def invoke(self, authorization_digest, request_id=None, trace_id=None):
        return self._client.call("model.invoke", {
            "authorizationDigest":authorization_digest,
            "requestId":request_id, "traceId":trace_id})


class IpcCoreModelGatewayClient:
    def __init__(self, client):
        self._client = client

    def prepare(self, authorization_digest, request_id, trace_id):
        return self._client.call("model.prepare", {
            "authorizationDigest":authorization_digest,
            "requestId":request_id, "traceId":trace_id})

    def record(self, authorization_digest, attempt_digest, started_at,
               ended_at, outcome, response, provider_request_ref, usage):
        return self._client.call("model.record", {
            "authorizationDigest":authorization_digest,
            "attemptDigest":attempt_digest, "startedAt":started_at,
            "endedAt":ended_at, "outcome":outcome, "response":response,
            "providerRequestRef":provider_request_ref, "usage":usage})
