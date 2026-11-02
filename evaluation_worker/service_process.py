"""Process entrypoints for the isolated Factory evaluation flow."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from evaluation_worker.gateway import (ModelEnvironment, OpenJiuwenModelGateway)
from evaluation_worker.service_boundary import (EvaluationCoreBoundary,
    EvaluationGatewayBoundary, IpcCandidateQueryClient,
    IpcCoreModelGatewayClient, IpcGatewayClient,
    IpcModelAuthorizationClient, ServiceCredentials, UnixEvaluationClient,
    UnixEvaluationServer)
from evaluation_worker.worker import CandidateEvaluationWorker
from evaluation_worker.service_task import (managed_runtime_versions,
                                             trusted_task_binding,
                                             validate_service_task)
from knowledge_core.core import Actor
from knowledge_core.documents import DocumentCore
from m2.ragflow import Ragflow


def _json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    return value


def _token(path):
    path = Path(path)
    stat = path.stat()
    if path.is_symlink() or not path.is_file() or stat.st_mode & 0o077:
        raise ValueError("EVALUATION_SERVICE_CREDENTIAL_PERMISSIONS_INVALID")
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("EVALUATION_SERVICE_CREDENTIAL_INVALID")
    return token


def _actor(config, role, privileges):
    value = config["actors"][role]
    if set(value) != {"principal", "authority"}:
        raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    return Actor(config["tenant"], value["principal"], value["authority"],
                 frozenset(privileges))


def _credentials(config):
    return ServiceCredentials(config["serviceCredentials"])


def _validate_config(config, role):
    common = {"tenant", "actors", "coreSocket", "gatewaySocket",
              "serviceCredentials"}
    role_fields = {
        "core":{"database", "retrievalPrivateConfig"},
        "gateway":{"gatewayTokenFile", "modelEnvironmentFile"},
        "worker":{"workerTokenFile"},
        "host":{"hostTokenFile"},
    }
    required = common | role_fields[role]
    optional = ({"fixedTask"} if role == "core" else
                {"caseIds"} if role == "worker" else set())
    if not required <= set(config) <= required | optional:
        raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    if (not isinstance(config.get("tenant"), str)
            or set(config.get("actors", {})) != {"host", "worker", "gateway"}):
        raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    for actor in config["actors"].values():
        if (not isinstance(actor, dict)
                or set(actor) != {"principal", "authority"}
                or any(not isinstance(value, str) or not value
                       for value in actor.values())):
            raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    _credentials(config)
    for field in (required - {"tenant", "actors", "serviceCredentials"}):
        if not isinstance(config.get(field), str) or not config[field]:
            raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    if (role == "worker" and "caseIds" in config
            and (not isinstance(config["caseIds"], list)
                 or any(not isinstance(value, str) or not value
                        for value in config["caseIds"]))):
        raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    return config


def _load_task(config, task_path=None):
    if task_path:
        if "fixedTask" in config:
            raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
        task = _json(task_path)
    else:
        task = config.get("fixedTask")
    return validate_service_task(task)


def _core_boundary(config, fixed):
    private = Path(config["retrievalPrivateConfig"])
    database = Path(config["database"])
    required_private = [private / "local-credentials.json",
                        private / "http-setup.json"]
    if (database.is_symlink() or not database.is_file()
            or private.is_symlink() or not private.is_dir()
            or any(path.is_symlink() or not path.is_file()
                   for path in required_private)):
        raise ValueError("EVALUATION_SERVICE_CONFIG_INVALID")
    versions = managed_runtime_versions()
    if versions != (fixed["pythonVersion"], fixed["openJiuwenVersion"]):
        raise ValueError("EVALUATION_SERVICE_RUNTIME_VERSION_MISMATCH")
    host = _actor(config, "host", {"model.egress.authorize",
                                    "candidate.validate"})
    core = DocumentCore(config["database"])
    try:
        trusted_task_binding(core, host, fixed)
    finally:
        core.close()
    return EvaluationCoreBoundary(
        lambda:DocumentCore(config["database"]),
        _actor(config, "worker", {"evaluation.execute"}),
        host,
        _actor(config, "gateway", {"model.receipt.record"}),
        lambda:Ragflow(private / "local-credentials.json",
                       private / "http-setup.json"),
        assignment_digest=fixed["assignmentDigest"],
        lease_digest=fixed["leaseDigest"],
        gateway_registration_digest=fixed["gatewayRegistrationDigest"],
        gateway_deployment_id=fixed["gatewayDeploymentId"],
        purpose=fixed["purpose"], redaction_profile=fixed["redactionProfile"],
        authorization_expires_at=fixed["authorizationExpiresAt"],
        candidate_digest=fixed["candidateDigest"],
        profile_digest=fixed["profileDigest"],
        test_set_digest=fixed["testSetDigest"],
        retrieval_digest=fixed["retrievalDigest"],
        worker_build_digest=fixed["workerBuildDigest"],
        python_version=fixed["pythonVersion"],
        openjiuwen_version=fixed["openJiuwenVersion"],
        gateway_runtime_identity=fixed["gatewayRuntimeIdentity"])


def serve_core(args):
    config = _validate_config(_json(args.config), "core")
    fixed = _load_task(config, args.task)
    server = UnixEvaluationServer(config["coreSocket"], _credentials(config),
                                  _core_boundary(config, fixed))
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


def serve_gateway(args):
    config = _validate_config(_json(args.config), "gateway")
    token = _token(config["gatewayTokenFile"])
    core = UnixEvaluationClient(config["coreSocket"], "gateway", token)
    environment = ModelEnvironment.from_env_file(config["modelEnvironmentFile"])
    gateway = OpenJiuwenModelGateway(
        IpcCoreModelGatewayClient(core), environment)
    boundary = EvaluationGatewayBoundary(gateway)
    server = UnixEvaluationServer(config["gatewaySocket"], _credentials(config),
                                  boundary)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        boundary.close()


def run_worker(args):
    config = _validate_config(_json(args.config), "worker")
    fixed = _load_task(config, args.task)
    if "caseIds" in config and config["caseIds"] != fixed["caseIds"]:
        raise ValueError("EVALUATION_SERVICE_TASK_BINDING_MISMATCH")
    if managed_runtime_versions() != (fixed["pythonVersion"],
                                      fixed["openJiuwenVersion"]):
        raise ValueError("EVALUATION_SERVICE_RUNTIME_VERSION_MISMATCH")
    token = _token(config["workerTokenFile"])
    core = UnixEvaluationClient(config["coreSocket"], "worker", token)
    gateway = UnixEvaluationClient(config["gatewaySocket"], "worker", token)
    core.wait_until_ready()
    gateway.wait_until_ready()
    worker = CandidateEvaluationWorker(
        IpcCandidateQueryClient(core), IpcModelAuthorizationClient(core),
        IpcGatewayClient(gateway))
    result = asyncio.run(worker.run(fixed["caseIds"]))
    output = Path(args.output)
    if (output.parent.is_symlink() or not output.parent.is_dir()
            or output.parent.stat().st_mode & 0o007):
        raise ValueError("EVALUATION_HANDOFF_DIRECTORY_INVALID")
    output.write_text(json.dumps({"runs":result}, ensure_ascii=False,
                                 indent=2) + "\n", encoding="utf-8")
    os.chmod(output, 0o640)


def finalize(args):
    config = _validate_config(_json(args.config), "host")
    token = _token(config["hostTokenFile"])
    runs = _json(args.runs)
    client = UnixEvaluationClient(config["coreSocket"], "host", token)
    result = client.call("evaluation.finalize", {"runs":runs["runs"]})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    os.chmod(output, 0o600)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name, function in (("core", serve_core), ("gateway", serve_gateway)):
        item = sub.add_parser(name); item.add_argument("--config", required=True)
        if name == "core":
            item.add_argument("--task")
        item.set_defaults(function=function)
    item = sub.add_parser("worker")
    item.add_argument("--config", required=True); item.add_argument("--task", required=True)
    item.add_argument("--output", required=True)
    item.set_defaults(function=run_worker)
    item = sub.add_parser("finalize")
    item.add_argument("--config", required=True); item.add_argument("--runs", required=True)
    item.add_argument("--output", required=True); item.set_defaults(function=finalize)
    args = parser.parse_args(); args.function(args)


if __name__ == "__main__":
    main()
