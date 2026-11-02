"""Create a bounded service-evaluation task from an existing frozen assignment."""
import argparse
from dataclasses import fields
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore


PRIVILEGES = frozenset({"evaluation.manage", "evaluation.lease.issue"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--template-assignment", required=True)
    parser.add_argument("--gateway-registration", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tenant", default="m2-isolated")
    parser.add_argument("--host-principal", default="quality-author")
    parser.add_argument("--host-authority", default="factory-quality-authority-v1")
    parser.add_argument("--worker-principal", default="factory-evaluation-worker")
    parser.add_argument("--worker-authority", default="worker-build-pr12")
    parser.add_argument("--worker-git-sha", required=True)
    parser.add_argument("--lifetime-minutes", type=int, default=90)
    args = parser.parse_args()
    if not 5 <= args.lifetime_minutes <= 240:
        parser.error("lifetime must be between 5 and 240 minutes")

    host = Actor(args.tenant, args.host_principal, args.host_authority, PRIVILEGES)
    core = DocumentCore(args.database)
    try:
        template = core._get(host, args.template_assignment,
                             "document-evaluation-assignment")
        gateway = core._get(host, args.gateway_registration,
                            "model-gateway-registration")
        if len(gateway["deployments"]) != 1:
            raise ValueError("ONE_GATEWAY_DEPLOYMENT_REQUIRED")
        context_values = dict(template["businessContext"])
        context_values["source"] = "trusted-evaluation-service-host"
        allowed = {item.name for item in fields(BusinessContext)}
        context = BusinessContext(**{key:value for key, value in context_values.items()
                                     if key in allowed})
        expires = (datetime.now(timezone.utc)
                   + timedelta(minutes=args.lifetime_minutes)).isoformat()
        suffix = uuid4().hex
        assignment = core.create_evaluation_assignment(
            host, "service-evaluation-" + suffix, 1,
            template["candidateDigest"], template["testSetDigest"],
            template["profileDigest"], template["retrievalEvaluationDigest"],
            template["classificationDigest"], template["modelSelectionDigest"],
            template["promptTemplateDigest"], context, expires)
        worker_build = hashlib.sha256(args.worker_git_sha.encode()).hexdigest()
        lease = core.issue_evaluation_lease(
            host, "service-worker-lease-" + suffix, 1, assignment,
            args.worker_principal, args.worker_authority, worker_build, expires,
            "service-nonce-" + suffix)
        assignment_body = core._get(host, assignment,
                                    "document-evaluation-assignment")
        deployment = gateway["deployments"][0]
        runtime_identity = {**deployment,
            "gatewayBuildDigest":gateway["buildDigest"],
            "adapterVersion":gateway["adapterVersion"],
            "openJiuwenVersion":gateway["openJiuwenVersion"],
            "qualificationDigest":gateway["qualificationDigest"]}
        result = {"assignmentDigest":assignment, "leaseDigest":lease,
            "candidateDigest":template["candidateDigest"],
            "profileDigest":template["profileDigest"],
            "testSetDigest":template["testSetDigest"],
            "retrievalDigest":template["retrievalEvaluationDigest"],
            "gatewayRegistrationDigest":args.gateway_registration,
            "gatewayDeploymentId":deployment["id"],
            "gatewayRuntimeIdentity":runtime_identity,
            "caseIds":assignment_body["caseIds"],
            "workerBuildDigest":worker_build, "expiresAt":expires}
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.output.write_text(json.dumps(result, ensure_ascii=False,
                                          indent=2) + "\n", encoding="utf-8")
    finally:
        core.close()


if __name__ == "__main__":
    main()
