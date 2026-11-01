"""Run the fixed Factory Worker flow against an isolated Core database copy."""
import argparse
import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evaluation_worker import (CandidateEvaluationWorker, ModelEnvironment,
                               OpenJiuwenModelGateway)
from evaluation_worker.gateway import build_openjiuwen_model
from knowledge_core.contracts import digest
from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore
from m2.ragflow import Ragflow
from tests.support import AUTHOR as BASE_AUTHOR


PRIVILEGES = BASE_AUTHOR.privileges | {
    'document.approve', 'source.classify', 'evaluation.manage',
    'evaluation.lease.issue', 'model.gateway.manage', 'model.egress.authorize',
}
MANAGER = replace(BASE_AUTHOR, privileges=PRIVILEGES)
WORKER = Actor(MANAGER.tenant, 'factory-evaluation-worker', 'worker-build-pr12',
               frozenset({'evaluation.execute'}))
GATEWAY = Actor(MANAGER.tenant, 'factory-model-gateway', 'gateway-pr12',
                frozenset({'model.receipt.record'}))


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
    args = parser.parse_args()

    environment = ModelEnvironment.from_env_file(args.model_env)
    model_config_digest = digest({
        'provider':'volcengine', 'modelRef':environment.model_name,
        'apiBase':environment.api_base})
    worker_build_digest = sha256_bytes(args.worker_git_sha.encode())
    lock_digest = sha256_bytes((Path(__file__).parents[1] /
                                'evaluation_worker/requirements.lock').read_bytes())
    now = datetime.now(timezone.utc)
    expires = iso(now + timedelta(hours=2))
    core = DocumentCore(args.database)
    ragflow = model = None
    try:
        candidate = core._get(MANAGER, args.candidate, 'document-candidate')
        index = core._get(MANAGER, candidate['indexDigest'], 'document-index')
        policy_revision, policy_digest = core._head(MANAGER, 'policy', 'current')
        policy = core._get(MANAGER, policy_digest, 'active-policy')
        updated = json.loads(json.dumps(policy))
        updated['revision'] = policy_revision + 1
        grant = {'principal':WORKER.principal,
                 'resource':'source:' + core._get(
                     MANAGER, index['sourceDigest'], 'source-revision')['id'],
                 'actions':['source_read']}
        if grant not in updated['grants']:
            updated['grants'].append(grant)
        core.set_policy(MANAGER, updated, policy_revision)

        classification = core.register_source_classification(
            MANAGER, 'pr12-source-classification', 1, index['sourceDigest'],
            'PUBLIC', True, ['volcengine'], ['cn-beijing'], ['factory-dev'])
        prompt = core.register_evaluation_prompt_template(
            MANAGER, 'pr12-grounded-answer', 1,
            '你是制度问答评测器。仅根据提供的已核验原文回答；依据不足时明确拒答。',
            '先给直接结论，再列出关键事实，并明确引用条款编号。不得补充原文没有的信息。')
        context = BusinessContext('2026-11-15', 'CN-BJ', 'demo-bank',
                                  'business-loan', 'answer-quality',
                                  'factory-worker-acceptance')
        assignment = core.create_evaluation_assignment(
            MANAGER, 'pr12-real-evaluation', 1, args.candidate, args.test_set,
            args.profile, args.retrieval, classification, model_config_digest,
            prompt, context, expires)
        lease = core.issue_evaluation_lease(
            MANAGER, 'pr12-real-worker-lease', 1, assignment,
            WORKER.principal, WORKER.authority, expires, 'pr12-real-nonce')
        gateway_registration = core.register_model_gateway(
            MANAGER, 'pr12-openjiuwen-gateway', 1, GATEWAY.principal,
            worker_build_digest, 'openjiuwen-model-v0.1', ['volcengine'],
            [environment.model_name], ['cn-beijing'], GATEWAY.authority,
            lock_digest)
        assignment_body = core._get(
            MANAGER, assignment, 'document-evaluation-assignment')

        ragflow = Ragflow(args.private_config / 'local-credentials.json',
                          args.private_config / 'http-setup.json')
        model = build_openjiuwen_model(environment)
        gateway = OpenJiuwenModelGateway(
            core, GATEWAY, gateway_registration, model)
        def authorize(candidate_receipt):
            case_id = candidate_receipt['caseId']
            return core.authorize_model_egress(
                MANAGER, 'pr12-egress-' + case_id, 1, assignment,
                candidate_receipt['receiptDigest'], 'volcengine',
                environment.model_name, model_config_digest, 'cn-beijing',
                'answer-quality', 'factory-dev', True, 'source-only', expires)

        worker = CandidateEvaluationWorker(
            core, WORKER, gateway, ragflow, authorize)
        runs = asyncio.run(worker.run(
            assignment, lease, assignment_body['caseIds']))
        runtime = core.register_factory_evaluation_runtime_evidence(
            MANAGER, assignment, lease, worker_build_digest, '3.12',
            '0.1.17.post1', runs)
        answer = core.register_answer_evaluation(
            MANAGER, args.candidate, args.profile, args.test_set,
            args.retrieval, runtime)
        admission = core.assess_document_quality(
            MANAGER, args.candidate, args.profile, args.test_set,
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
                MANAGER, admission, 'document-quality-admission'),
            'runtimeEvidence':core._get(
                MANAGER, runtime, 'document-factory-evaluation-runtime-evidence'),
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
