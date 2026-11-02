"""Create a bounded service-evaluation task from an existing frozen assignment."""
import argparse
from dataclasses import fields
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from evaluation_worker.service_task import (managed_runtime_versions,
                                             validate_service_task)
from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore


PRIVILEGES = frozenset({"evaluation.manage", "evaluation.lease.issue",
                        "model.egress.authorize"})


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
        core._get(host, args.gateway_registration, "model-gateway-registration")
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
        python_version, openjiuwen_version = managed_runtime_versions()
        result = {"schemaVersion":"factory-evaluation-service-task.v0.1",
            **core.evaluation_service_task_binding(
                host, assignment, lease, args.gateway_registration,
                python_version, openjiuwen_version)}
        validate_service_task(result)
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.output.write_text(json.dumps(result, ensure_ascii=False,
                                          indent=2) + "\n", encoding="utf-8")
    finally:
        core.close()


if __name__ == "__main__":
    main()
