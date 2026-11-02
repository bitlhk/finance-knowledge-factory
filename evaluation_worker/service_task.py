"""Closed contract for one managed evaluation-service task."""
from datetime import datetime
from importlib.metadata import version
import platform

from jsonschema import Draft202012Validator

from knowledge_core.contracts import Rejected, canonical


HASH = {"type":"string", "pattern":"^[a-f0-9]{64}$"}
ID = {"type":"string", "pattern":"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$"}
TIMESTAMP = {"type":"string", "format":"date-time", "minLength":20,
             "maxLength":64}
RUNTIME_IDENTITY = {
    "type":"object",
    "properties":{
        "id":ID, "provider":ID, "modelRef":ID, "modelConfigDigest":HASH,
        "endpointOrigin":{"type":"string", "minLength":1, "maxLength":2048},
        "region":ID, "executionZone":ID, "external":{"type":"boolean"},
        "gatewayBuildDigest":HASH, "adapterVersion":ID,
        "openJiuwenVersion":{"const":"0.1.17.post1"},
        "qualificationDigest":HASH,
    },
    "required":["id", "provider", "modelRef", "modelConfigDigest",
                "endpointOrigin", "region", "executionZone", "external",
                "gatewayBuildDigest", "adapterVersion", "openJiuwenVersion",
                "qualificationDigest"],
    "additionalProperties":False,
}
SERVICE_TASK_SCHEMA = {
    "$schema":"https://json-schema.org/draft/2020-12/schema",
    "$id":"urn:finance-knowledge-factory:evaluation-service-task:v0.1",
    "type":"object",
    "properties":{
        "schemaVersion":{"const":"factory-evaluation-service-task.v0.1"},
        "assignmentDigest":HASH, "leaseDigest":HASH, "candidateDigest":HASH,
        "profileDigest":HASH, "testSetDigest":HASH, "retrievalDigest":HASH,
        "gatewayRegistrationDigest":HASH, "gatewayDeploymentId":ID,
        "gatewayRuntimeIdentity":RUNTIME_IDENTITY,
        "caseIds":{"type":"array", "items":ID, "minItems":1,
                   "maxItems":1000, "uniqueItems":True},
        "workerBuildDigest":HASH, "purpose":ID,
        "redactionProfile":{"const":"source-only"},
        "authorizationExpiresAt":TIMESTAMP,
        "pythonVersion":{"const":"3.12"},
        "openJiuwenVersion":{"const":"0.1.17.post1"},
        "expiresAt":TIMESTAMP,
    },
    "required":["schemaVersion", "assignmentDigest", "leaseDigest",
                "candidateDigest", "profileDigest", "testSetDigest",
                "retrievalDigest", "gatewayRegistrationDigest",
                "gatewayDeploymentId", "gatewayRuntimeIdentity", "caseIds",
                "workerBuildDigest", "purpose", "redactionProfile",
                "authorizationExpiresAt", "pythonVersion",
                "openJiuwenVersion", "expiresAt"],
    "additionalProperties":False,
}


def managed_runtime_versions():
    python_version = ".".join(platform.python_version_tuple()[:2])
    try:
        openjiuwen_version = version("openjiuwen")
    except Exception as error:
        raise Rejected("OPENJIUWEN_VERSION_MISMATCH") from error
    return python_version, openjiuwen_version


def validate_service_task(task):
    if not isinstance(task, dict):
        raise Rejected("EVALUATION_SERVICE_TASK_INVALID")
    errors = sorted(Draft202012Validator(SERVICE_TASK_SCHEMA).iter_errors(task),
                    key=lambda item:list(item.path))
    if errors:
        raise Rejected("EVALUATION_SERVICE_TASK_INVALID")
    try:
        authorization_expiry = datetime.fromisoformat(
            task["authorizationExpiresAt"].replace("Z", "+00:00"))
        task_expiry = datetime.fromisoformat(
            task["expiresAt"].replace("Z", "+00:00"))
    except ValueError:
        raise Rejected("EVALUATION_SERVICE_TASK_INVALID") from None
    if (authorization_expiry.tzinfo is None or task_expiry.tzinfo is None
            or authorization_expiry > task_expiry):
        raise Rejected("EVALUATION_SERVICE_TASK_INVALID")
    canonical(task)
    return task


def trusted_task_binding(core, actor, task):
    """Recompute and compare every task field before Core opens its socket."""
    validate_service_task(task)
    expected = core.evaluation_service_task_binding(
        actor, task["assignmentDigest"], task["leaseDigest"],
        task["gatewayRegistrationDigest"], task["pythonVersion"],
        task["openJiuwenVersion"])
    expected = {"schemaVersion":"factory-evaluation-service-task.v0.1",
                **expected}
    if task != expected:
        raise Rejected("EVALUATION_SERVICE_TASK_BINDING_MISMATCH")
    return task
