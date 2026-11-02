import asyncio
import json
import os
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evaluation_worker import (CandidateEvaluationWorker, EvaluationCoreBoundary,
    EvaluationGatewayBoundary, IpcCandidateQueryClient,
    IpcCoreModelGatewayClient, IpcGatewayClient,
    IpcModelAuthorizationClient, OpenJiuwenModelGateway, ServiceCredentials,
    UnixEvaluationClient, UnixEvaluationServer, token_digest)
from evaluation_worker.service_process import (_core_boundary, _load_task,
                                               _validate_config)
from evaluation_worker.service_task import validate_service_task
from knowledge_core.contracts import Rejected
from knowledge_core.documents import DocumentCore
from tests.test_factory_evaluation_worker import (ENVIRONMENT, GATEWAY, MANAGER,
                                                   WORKER, prepare)
from tools import prepare_evaluation_service_task


def _credentials():
    return {role:{'uid':position + 1000,
                  'tokenDigest':token_digest((role + '-token-') * 4)}
            for position, role in enumerate(('host', 'worker', 'gateway'))}


def _core_config(tmp_path, database, private):
    return {
        'tenant':MANAGER.tenant,
        'actors':{
            'host':{'principal':MANAGER.principal,
                    'authority':MANAGER.authority},
            'worker':{'principal':WORKER.principal,
                      'authority':WORKER.authority},
            'gateway':{'principal':GATEWAY.principal,
                       'authority':GATEWAY.authority},
        },
        'coreSocket':str(tmp_path / 'core.sock'),
        'gatewaySocket':str(tmp_path / 'gateway.sock'),
        'database':str(database),
        'retrievalPrivateConfig':str(private),
        'serviceCredentials':_credentials(),
    }


def _generated_task(tmp_path):
    core, evidence, values = prepare(tmp_path)
    database = tmp_path / 'core.db'
    core.close()
    output = tmp_path / 'task.json'
    arguments = [
        'prepare_evaluation_service_task',
        '--database', str(database),
        '--template-assignment', values['assignment'],
        '--gateway-registration', values['gateway'],
        '--output', str(output), '--tenant', MANAGER.tenant,
        '--host-principal', MANAGER.principal,
        '--host-authority', MANAGER.authority,
        '--worker-principal', WORKER.principal,
        '--worker-authority', WORKER.authority,
        '--worker-git-sha', '67352c7a8cbb7b36c66b278683297950df0b4828',
        '--lifetime-minutes', '5',
    ]
    with patch.object(sys, 'argv', arguments), patch.object(
            prepare_evaluation_service_task, 'managed_runtime_versions',
            return_value=('3.12', '0.1.17.post1')):
        prepare_evaluation_service_task.main()
    return (database, output, json.loads(output.read_text(encoding='utf-8')),
            evidence)


def test_generated_task_is_complete_and_starts_core_without_json_merge(tmp_path):
    database, output, task, _ = _generated_task(tmp_path)
    assert task['schemaVersion'] == 'factory-evaluation-service-task.v0.1'
    assert task['purpose'] == 'condition-check'
    assert task['redactionProfile'] == 'source-only'
    assert task['authorizationExpiresAt'] == task['expiresAt']
    assert task['pythonVersion'] == '3.12'
    assert task['openJiuwenVersion'] == '0.1.17.post1'

    private = tmp_path / 'ragflow'
    private.mkdir()
    (private / 'local-credentials.json').write_text('{}\n', encoding='utf-8')
    (private / 'http-setup.json').write_text('{}\n', encoding='utf-8')
    config = _validate_config(_core_config(tmp_path, database, private), 'core')
    loaded = _load_task(config, output)
    with patch('evaluation_worker.service_process.managed_runtime_versions',
               return_value=('3.12', '0.1.17.post1')):
        boundary = _core_boundary(config, loaded)
    assert boundary._purpose == task['purpose']


@pytest.mark.parametrize(('field', 'value'), [
    ('purpose', None),
    ('pythonVersion', '3.11'),
    ('openJiuwenVersion', '0.1.16'),
    ('authorizationExpiresAt', 'not-a-time'),
])
def test_service_task_schema_rejects_missing_types_and_versions(tmp_path, field,
                                                                value):
    _, _, task, _ = _generated_task(tmp_path)
    if value is None:
        task.pop(field)
    else:
        task[field] = value
    with pytest.raises(Rejected, match='EVALUATION_SERVICE_TASK_INVALID'):
        validate_service_task(task)


def test_core_startup_rejects_task_binding_tamper_before_socket(tmp_path):
    database, _, task, _ = _generated_task(tmp_path)
    task['purpose'] = 'other-purpose'
    validate_service_task(task)
    private = tmp_path / 'ragflow'
    private.mkdir()
    for name in ('local-credentials.json', 'http-setup.json'):
        (private / name).write_text('{}\n', encoding='utf-8')
    config = _validate_config(_core_config(tmp_path, database, private), 'core')
    with patch('evaluation_worker.service_process.managed_runtime_versions',
               return_value=('3.12', '0.1.17.post1')):
        with pytest.raises(
                Rejected, match='EVALUATION_SERVICE_TASK_BINDING_MISMATCH'):
            _core_boundary(config, task)
    assert not (tmp_path / 'core.sock').exists()


def test_core_config_rejects_unknown_fields():
    config = {'unexpected':True}
    with pytest.raises(ValueError, match='EVALUATION_SERVICE_CONFIG_INVALID'):
        _validate_config(config, 'core')


def test_generated_task_runs_core_worker_gateway_finalize_after_restart(tmp_path):
    database, _, task, evidence = _generated_task(tmp_path)
    tokens = {role:(role + '-integration-token-') * 3
              for role in ('host', 'worker', 'gateway')}
    records = {role:{'uid':os.getuid(),
                    'tokenDigest':token_digest(tokens[role])}
               for role in tokens}
    credentials = ServiceCredentials(records)
    kwargs = dict(
        assignment_digest=task['assignmentDigest'],
        lease_digest=task['leaseDigest'],
        gateway_registration_digest=task['gatewayRegistrationDigest'],
        gateway_deployment_id=task['gatewayDeploymentId'],
        purpose=task['purpose'], redaction_profile=task['redactionProfile'],
        authorization_expires_at=task['authorizationExpiresAt'],
        candidate_digest=task['candidateDigest'],
        profile_digest=task['profileDigest'],
        test_set_digest=task['testSetDigest'],
        retrieval_digest=task['retrievalDigest'],
        worker_build_digest=task['workerBuildDigest'],
        python_version=task['pythonVersion'],
        openjiuwen_version=task['openJiuwenVersion'],
        gateway_runtime_identity=task['gatewayRuntimeIdentity'])

    def make_core_server():
        boundary = EvaluationCoreBoundary(
            lambda:DocumentCore(database), WORKER, MANAGER, GATEWAY,
            lambda:evidence, **kwargs)
        server = UnixEvaluationServer(
            tmp_path / 'core.sock', credentials, boundary,
            enforce_distinct_users=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    core_server, core_thread = make_core_server()
    core_server.shutdown(); core_server.server_close(); core_thread.join()
    core_server, core_thread = make_core_server()

    class Model:
        async def invoke(self, messages, **model_kwargs):
            return SimpleNamespace(
                content='根据第一条，合成客服服务时间为每日09:00至17:00。',
                usage_metadata=None, metadata={'request_id':'integration-provider'})

    gateway_core = UnixEvaluationClient(
        core_server.path, 'gateway', tokens['gateway'])
    gateway = OpenJiuwenModelGateway(
        IpcCoreModelGatewayClient(gateway_core), ENVIRONMENT,
        lambda unused:Model())
    gateway_boundary = EvaluationGatewayBoundary(gateway)
    gateway_server = UnixEvaluationServer(
        tmp_path / 'gateway.sock', credentials, gateway_boundary,
        enforce_distinct_users=False)
    gateway_thread = threading.Thread(
        target=gateway_server.serve_forever, daemon=True)
    gateway_thread.start()
    try:
        worker_core = UnixEvaluationClient(
            core_server.path, 'worker', tokens['worker'])
        worker_gateway = UnixEvaluationClient(
            gateway_server.path, 'worker', tokens['worker'])
        worker = CandidateEvaluationWorker(
            IpcCandidateQueryClient(worker_core),
            IpcModelAuthorizationClient(worker_core),
            IpcGatewayClient(worker_gateway))
        runs = asyncio.run(worker.run(task['caseIds']))
        host = UnixEvaluationClient(core_server.path, 'host', tokens['host'])
        final = host.call('evaluation.finalize', {'runs':runs})
        assert set(final) == {'runtimeEvidenceDigest', 'answerEvaluationDigest',
                              'qualityAdmissionDigest'}
    finally:
        gateway_server.shutdown(); gateway_server.server_close()
        gateway_thread.join(); gateway_boundary.close()
        core_server.shutdown(); core_server.server_close(); core_thread.join()
