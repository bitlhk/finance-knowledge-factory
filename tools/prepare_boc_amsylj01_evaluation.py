"""Prepare one isolated AMSYLJ01 three-service evaluation.

The input database must be an isolated copy containing an already-qualified
Gateway registration and model selection. This tool creates a new Candidate,
RAGFlow index, frozen 18-case assignment, and one-use Worker lease. It does not
publish a Manifest or alter the formal Knowledge Factory database.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business_knowledge.boc_amsylj01 import build_bundle, produce_candidate
from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore
from m2.ragflow import Ragflow
from quality.retrieval_profiles import PROFILES


PRIVILEGES = frozenset({
    "policy.manage", "source.register", "source.activate", "gold.manage",
    "recipe.edit", "artifact.produce", "candidate.validate",
    "document.approve", "manifest.publish", "binding.manage",
    "source.classify", "evaluation.manage", "evaluation.lease.issue",
    "model.gateway.manage", "model.egress.authorize",
})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--private-config", type=Path, required=True)
    parser.add_argument("--template-assignment", required=True)
    parser.add_argument("--gateway-registration", required=True)
    parser.add_argument("--worker-git-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path,
                        default=Path("examples/business/customer-manager"))
    parser.add_argument("--lifetime-minutes", type=int, default=120)
    args = parser.parse_args()
    if not 30 <= args.lifetime_minutes <= 240:
        parser.error("lifetime must be between 30 and 240 minutes")

    actor = Actor("m2-isolated", "quality-author",
                  "factory-quality-authority-v1", PRIVILEGES)
    core = DocumentCore(args.database)
    try:
        template = core._get(actor, args.template_assignment,
                             "document-evaluation-assignment")
        gateway = core._get(actor, args.gateway_registration,
                            "model-gateway-registration")
        if len(gateway["deployments"]) != 1:
            raise ValueError("ONE_GATEWAY_DEPLOYMENT_REQUIRED")

        revision, policy_digest = core._head(actor, "policy", "current")
        policy = core._get(actor, policy_digest, "active-policy")
        grants = list(policy["grants"])
        for principal in ("quality-author", "factory-evaluation-worker",
                          "factory-model-gateway"):
            grants.append({"principal":principal,
                "resource":"source:boc-wealth-service-amsylj01-source",
                "actions":["source_read"]})
        for principal in ("quality-author", "knowledge-agent"):
            grants.append({"principal":principal,
                "resource":"product:boc-wealth-service-amsylj01",
                "actions":["consume", "history"]})
        core.set_policy(actor, {"schemaVersion":"active-policy.v0.1",
            "revision":revision + 1, "grants":grants}, revision)

        bundle = build_bundle(args.root / "amsylj01/sources")
        business = json.loads((args.root /
            "boc-wealth-manager-test-set-v0.1.json").read_text(encoding="utf-8"))
        client = Ragflow(args.private_config / "local-credentials.json",
                         args.private_config / "http-setup.json")
        values = produce_candidate(core, actor, bundle, {
            "regions":["CN"], "institutions":["bank-of-china"],
            "products":["AMSYLJ01"],
            "purposes":["customer-manager-service-preparation"],
            "validFrom":"2025-02-28", "validTo":None,
            "timezone":"Asia/Shanghai"}, business, ["knowledge-agent"], client)
        core.activate_source(actor, values["sourceDigest"], "2025-02-28")
        validation = core.validate_document(
            actor, values["candidateDigest"], client)
        profile = core.register_quality_profile(
            actor, "boc-amsylj01-financial-document-v02", 1,
            PROFILES["financial-document-v02"])
        tests = core.register_quality_test_set(
            actor, values["candidateDigest"], values["qualityTestSet"], 1)
        retrieval = core.evaluate_quality_retrieval(
            actor, values["candidateDigest"], profile, tests, client)
        classification = core.register_source_classification(
            actor, "boc-amsylj01-public-source", 1,
            values["sourceDigest"], "PUBLIC", True,
            ["volcengine"], ["cn-beijing"], ["factory-dev"])
        prompt = core.register_evaluation_prompt_template(
            actor, "boc-amsylj01-grounded-answer", 1,
            "仅根据提供的中国银行公开资料原文回答；证据不足或涉及实时状态时明确说明需要核实。",
            "先给直接结论，再列依据编号；不得补造当前客户评级、在售状态、收益率或渠道状态。")
        expires = (datetime.now(timezone.utc)
                   + timedelta(minutes=args.lifetime_minutes)).isoformat()
        context = BusinessContext(
            business_date="2026-11-02", region="CN",
            institution="bank-of-china", product="AMSYLJ01",
            purpose="customer-manager-service-preparation",
            source="trusted-evaluation-service-host",
            timezone="Asia/Shanghai")
        assignment = core.create_evaluation_assignment(
            actor, "boc-amsylj01-evaluation", 1,
            values["candidateDigest"], tests, profile, retrieval,
            classification, template["modelSelectionDigest"], prompt,
            context, expires)
        worker_build = hashlib.sha256(
            args.worker_git_sha.encode("ascii")).hexdigest()
        lease = core.issue_evaluation_lease(
            actor, "boc-amsylj01-worker-lease", 1, assignment,
            "factory-evaluation-worker", "worker-build-pr12",
            worker_build, expires, "boc-amsylj01-worker-lease-nonce")
        deployment = gateway["deployments"][0]
        runtime_identity = {**deployment,
            "gatewayBuildDigest":gateway["buildDigest"],
            "adapterVersion":gateway["adapterVersion"],
            "openJiuwenVersion":gateway["openJiuwenVersion"],
            "qualificationDigest":gateway["qualificationDigest"]}
        validation_body = core._get(actor, validation, "document-validation")
        retrieval_body = core._get(
            actor, retrieval, "document-retrieval-evaluation")
        result = {**{key:value for key,value in values.items()
                     if key != "qualityTestSet"},
            "validationDigest":validation, "validationPassed":validation_body["passed"],
            "profileDigest":profile, "testSetDigest":tests,
            "retrievalDigest":retrieval,
            "retrievalReport":retrieval_body["report"],
            "classificationDigest":classification,
            "promptTemplateDigest":prompt,
            "assignmentDigest":assignment, "leaseDigest":lease,
            "gatewayRegistrationDigest":args.gateway_registration,
            "gatewayDeploymentId":deployment["id"],
            "gatewayRuntimeIdentity":runtime_identity,
            "workerBuildDigest":worker_build, "expiresAt":expires,
            "caseIds":[item["caseId"] for item in values["qualityTestSet"]["cases"]],
            "ragflowOperations":client.operations}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False,
                                          indent=2) + "\n", encoding="utf-8")
    finally:
        core.close()


if __name__ == "__main__":
    main()
