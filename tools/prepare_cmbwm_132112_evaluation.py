"""Prepare the workbench-created 132112 Candidate for isolated service evaluation."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business_knowledge.cmbwm_132112 import PRODUCT_ID, quality_test_set
from evaluation_worker.gateway import (ModelDeployment, ModelEnvironment,
                                       model_config_digest)
from evaluation_worker.service_task import (managed_runtime_versions,
                                             validate_service_task)
from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore
from m2.ragflow import Ragflow
from quality.retrieval_profiles import PROFILES


PRIVILEGES = frozenset({
    "policy.manage", "source.activate", "artifact.produce", "candidate.validate",
    "source.classify", "evaluation.manage", "evaluation.lease.issue",
    "model.gateway.manage", "model.egress.authorize",
})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--private-config", type=Path, required=True)
    parser.add_argument("--model-env", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--worker-git-sha", required=True)
    parser.add_argument("--profile", choices=("financial-document-v02", "financial-business-v03"),
                        default="financial-business-v03")
    parser.add_argument("--lifetime-minutes", type=int, default=120)
    args = parser.parse_args()
    if not 30 <= args.lifetime_minutes <= 240:
        parser.error("lifetime must be between 30 and 240 minutes")

    host = Actor("m2-isolated", "quality-author", "factory-quality-authority-v1",
                 PRIVILEGES)
    environment = ModelEnvironment.from_env_file(args.model_env)
    worker_build = hashlib.sha256(args.worker_git_sha.encode("ascii")).hexdigest()
    lock_digest = hashlib.sha256(
        (Path(__file__).parents[1] / "evaluation_worker/requirements.lock").read_bytes()).hexdigest()
    deployment = ModelDeployment(
        "volcengine-deepseek", "volcengine", environment.api_base,
        "cn-beijing", "factory-dev", True, worker_build,
        "openjiuwen-model-v0.1", lock_digest)
    core = DocumentCore(args.database)
    client = None
    try:
        candidate_object = core._get(host, args.candidate, "document-candidate")
        index = core._get(host, candidate_object["indexDigest"], "document-index")
        source = core._get(host, index["sourceDigest"], "source-revision")
        revision, policy_digest = core._head(host, "policy", "current")
        policy = core._get(host, policy_digest, "active-policy")
        grants = list(policy["grants"])
        for principal in ("quality-author", "factory-evaluation-worker"):
            grants.append({"principal":principal, "resource":"source:" + source["id"],
                           "actions":["source_read"]})
        grants.append({"principal":"quality-author", "resource":"product:" + PRODUCT_ID,
                       "actions":["consume", "history"]})
        grants = list({json.dumps(value, sort_keys=True):value for value in grants}.values())
        core.set_policy(host, {"schemaVersion":"active-policy.v0.1",
            "revision":revision + 1, "grants":grants}, revision)
        candidate, _, _, index = core._document_parts(host, args.candidate)
        core.activate_source(host, index["sourceDigest"], "2026-10-30")

        profile = core.register_quality_profile(
            host, "cmbwm-132112-" + args.profile, 1,
            PROFILES[args.profile])
        tests = core.register_quality_test_set(
            host, args.candidate, quality_test_set(index["sourceDigest"]), 1)
        client = Ragflow(args.private_config / "local-credentials.json",
                         args.private_config / "http-setup.json")
        retrieval = core.evaluate_quality_retrieval(
            host, args.candidate, profile, tests, client)
        classification = core.register_source_classification(
            host, "cmbwm-132112-public-source", 1, index["sourceDigest"],
            "PUBLIC", True, ["volcengine"], ["cn-beijing"], ["factory-dev"])
        prompt = core.register_evaluation_prompt_template(
            host, "cmbwm-132112-grounded-answer", 1,
            "仅根据已核验的招银理财132112产品文件回答。证据不足或涉及当前在售、额度、客户评级、交易日历及渠道状态时，明确说明需要通过业务系统核实。",
            "先给直接结论，再列证据编号和原文件位置。严格区分有权与必然、正常赎回与产品终止、零申购赎回费与无其他费用；不得承诺未来到账日期或客户购买资格。")
        gateway = core.register_model_gateway(
            host, "cmbwm-132112-openjiuwen-gateway", 1,
            "factory-model-gateway", deployment.gateway_build_digest,
            deployment.adapter_version, [deployment.registration(environment)],
            "gateway-pr12", deployment.qualification_digest)
        expires = (datetime.now(timezone.utc)
                   + timedelta(minutes=args.lifetime_minutes)).isoformat()
        context = BusinessContext("2026-11-02", "CN", "njcb-sales-channel",
            "cmbwm-132112", "customer-manager-service-preparation",
            "trusted-evaluation-service-host", "Asia/Shanghai")
        assignment = core.create_evaluation_assignment(
            host, "cmbwm-132112-evaluation", 1, args.candidate, tests, profile,
            retrieval, classification, model_config_digest("volcengine", environment),
            prompt, context, expires)
        lease = core.issue_evaluation_lease(
            host, "cmbwm-132112-worker-lease", 1, assignment,
            "factory-evaluation-worker", "worker-build-pr12", worker_build,
            expires, "cmbwm-132112-worker-nonce")
        python_version, openjiuwen_version = managed_runtime_versions()
        task = {"schemaVersion":"factory-evaluation-service-task.v0.1",
            **core.evaluation_service_task_binding(
                host, assignment, lease, gateway, python_version,
                openjiuwen_version)}
        validate_service_task(task)
        retrieval_body = core._get(host, retrieval, "document-retrieval-evaluation")
        result = {"candidateDigest":args.candidate, "sourceDigest":index["sourceDigest"],
            "profileDigest":profile, "testSetDigest":tests,
            "retrievalDigest":retrieval, "retrievalReport":retrieval_body["report"],
            "classificationDigest":classification, "promptTemplateDigest":prompt,
            "assignmentDigest":assignment, "leaseDigest":lease,
            "gatewayRegistrationDigest":gateway, "workerBuildDigest":worker_build,
            "expiresAt":expires, "caseIds":task["caseIds"],
            "ragflowOperations":client.operations}
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        args.task.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
    finally:
        if client is not None:
            client.token = None
        core.close()


if __name__ == "__main__":
    main()
