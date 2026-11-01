"""Run the fixed Factory Worker flow against an isolated Core database copy."""
import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evaluation_worker import (CandidateEvaluationWorker, CandidateQueryClient,
                               CoreModelGatewayClient, ModelAuthorizationClient,
                               ModelDeployment, ModelEnvironment,
                               OpenJiuwenModelGateway, model_config_digest)
from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore
from m2.ragflow import Ragflow
PRIVILEGES = frozenset({
    'policy.manage', 'source.register', 'source.activate', 'gold.manage',
    'recipe.edit', 'artifact.produce', 'candidate.validate', 'rule.approve',
    'manifest.publish', 'binding.manage', 'document.approve', 'source.classify',
    'evaluation.manage', 'evaluation.lease.issue', 'model.gateway.manage',
    'model.egress.authorize',
})


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def iso(value):
    return value.astimezone(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--private-config', type=Path, required=True)
    parser.add_argument('--model-env', type=Path, required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--test-set', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--retrieval', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker-git-sha', required=True)
    parser.add_argument('--tenant', default='m2-isolated')
    parser.add_argument('--manager-principal', default='quality-author')
    parser.add_argument('--manager-authority', default='factory-quality-authority-v1')
    args = parser.parse_args()

    manager = Actor(args.tenant, args.manager_principal, args.manager_authority,
                    PRIVILEGES)
    worker = Actor(args.tenant, 'factory-evaluation-worker', 'worker-build-pr12',
                   frozenset({'evaluation.execute'}))
    gateway_actor = Actor(args.tenant, 'factory-model-gateway', 'gateway-pr12',
                          frozenset({'model.receipt.record'}))

    environment = ModelEnvironment.from_env_file(args.model_env)
    selected_model_digest = model_config_digest('volcengine', environment)
    worker_build_digest = sha256_bytes(args.worker_git_sha.encode())
    lock_digest = sha256_bytes((Path(__file__).parents[1] /
                                'evaluation_worker/requirements.lock').read_bytes())
    now = datetime.now(timezone.utc)
    expires = iso(now + timedelta(hours=2))
    core = DocumentCore(args.database)
    ragflow = None
    try:
        candidate = core._get(manager, args.candidate, 'document-candidate')
        index = core._get(manager, candidate['indexDigest'], 'document-index')
        policy_revision, policy_digest = core._head(manager, 'policy', 'current')
        policy = core._get(manager, policy_digest, 'active-policy')
        updated = json.loads(json.dumps(policy))
        updated['revision'] = policy_revision + 1
        grant = {'principal':worker.principal,
                 'resource':'source:' + core._get(
                     manager, index['sourceDigest'], 'source-revision')['id'],
                 'actions':['source_read']}
        if grant not in updated['grants']:
            updated['grants'].append(grant)
        core.set_policy(manager, updated, policy_revision)

        classification = core.register_source_classification(
            manager, 'pr12-source-classification', 1, index['sourceDigest'],
            'PUBLIC', True, ['volcengine'], ['cn-beijing'], ['factory-dev'])
        prompt = core.register_evaluation_prompt_template(
            manager, 'pr12-grounded-answer', 1,
            '你是制度问答评测器。仅根据提供的已核验原文回答；依据不足时明确拒答。',
            '先给直接结论，再列出关键事实，并明确引用条款编号。不得补充原文没有的信息。')
        context = BusinessContext('2026-11-15', 'CN-BJ', 'demo-bank',
                                  'business-loan', 'answer-quality',
                                  'factory-worker-acceptance')
        assignment = core.create_evaluation_assignment(
            manager, 'pr12-real-evaluation', 1, args.candidate, args.test_set,
            args.profile, args.retrieval, classification, selected_model_digest,
            prompt, context, expires)
        lease = core.issue_evaluation_lease(
            manager, 'pr12-real-worker-lease', 1, assignment,
            worker.principal, worker.authority, worker_build_digest, expires,
            'pr12-real-nonce')
        deployment = ModelDeployment(
            'volcengine-deepseek', 'volcengine', environment.api_base,
            'cn-beijing', 'factory-dev', True, worker_build_digest,
            'openjiuwen-model-v0.1', lock_digest)
        gateway_registration = core.register_model_gateway(
            manager, 'pr12-openjiuwen-gateway', 1, gateway_actor.principal,
            deployment.gateway_build_digest, deployment.adapter_version,
            [deployment.registration(environment)], gateway_actor.authority,
            deployment.qualification_digest)
        assignment_body = core._get(
            manager, assignment, 'document-evaluation-assignment')

        ragflow = Ragflow(args.private_config / 'local-credentials.json',
                          args.private_config / 'http-setup.json')
        core_gateway = CoreModelGatewayClient(
            core, gateway_actor, gateway_registration,
            deployment.runtime_identity(environment))
        gateway = OpenJiuwenModelGateway(
            core_gateway, environment)

        evaluator = CandidateEvaluationWorker(
            CandidateQueryClient(core, worker, assignment, lease, ragflow),
            ModelAuthorizationClient(
                core, manager, assignment, gateway_registration, deployment.id,
                'answer-quality', 'source-only', expires),
            gateway)
        runs = asyncio.run(evaluator.run(assignment_body['caseIds']))
        runtime = core.register_factory_evaluation_runtime_evidence(
            manager, assignment, lease, worker_build_digest, '3.12',
            '0.1.17.post1', runs)
        answer = core.register_answer_evaluation(
            manager, args.candidate, args.profile, args.test_set,
            args.retrieval, runtime)
        admission = core.assess_document_quality(
            manager, args.candidate, args.profile, args.test_set,
            args.retrieval, answer)
        report = {
            'schemaVersion':'factory-worker-acceptance.v0.1',
            'workerGitSha':args.worker_git_sha,
            'workerBuildDigest':worker_build_digest,
            'requirementsLockDigest':lock_digest,
            'candidateDigest':args.candidate, 'assignmentDigest':assignment,
            'leaseDigest':lease, 'gatewayRegistrationDigest':gateway_registration,
            'runtimeEvidenceDigest':runtime, 'answerEvaluationDigest':answer,
            'qualityAdmissionDigest':admission,
            'qualityAdmission':core._get(
                manager, admission, 'document-quality-admission'),
            'runtimeEvidence':core._get(
                manager, runtime, 'document-factory-evaluation-runtime-evidence'),
            'completedAt':iso(datetime.now(timezone.utc)),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        print(json.dumps({key:report[key] for key in (
            'workerGitSha', 'candidateDigest', 'runtimeEvidenceDigest',
            'answerEvaluationDigest', 'qualityAdmissionDigest')},
            ensure_ascii=False))
    finally:
        if ragflow is not None:
            ragflow.token = None
        core.close()


if __name__ == '__main__':
    main()
