"""Core-owned contracts for evaluating unpublished document candidates.

The Worker can request evidence and submit receipt digests. It cannot create a
trusted model receipt, calculate quality metrics, or publish a product.
"""
from datetime import datetime, timezone
import ipaddress
import re
from urllib.parse import urlsplit

from .contracts import Rejected, canonical, digest, text_digest
from .core import Actor


_ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}')


def _now():
    return datetime.now(timezone.utc)


def _timestamp(value):
    if not isinstance(value, str):
        raise Rejected('EVALUATION_TIME_INVALID')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise Rejected('EVALUATION_TIME_INVALID') from None
    if parsed.tzinfo is None:
        raise Rejected('EVALUATION_TIME_INVALID')
    return parsed.astimezone(timezone.utc)


def _identifier(value, code='EVALUATION_REQUEST_INVALID'):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise Rejected(code)
    return value


def _endpoint_origin(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise Rejected('EVALUATION_MODEL_ENDPOINT_INVALID')
    parsed = urlsplit(value)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise Rejected('EVALUATION_MODEL_ENDPOINT_INVALID')
    if parsed.scheme == 'http' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise Rejected('EVALUATION_MODEL_ENDPOINT_INVALID')
    return value.rstrip('/')


def _endpoint_is_external(value):
    hostname = urlsplit(value).hostname
    if hostname == 'localhost':
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (address.is_private or address.is_loopback or address.is_link_local)


class FactoryEvaluationMixin:
    def register_evaluation_prompt_template(self, actor, template_id, revision,
                                            system_instruction,
                                            answer_instruction,
                                            max_evidence_items=3,
                                            max_answer_characters=12000):
        actor.require('evaluation.manage')
        with self.tx():
            return self._put(actor, 'document-evaluation-prompt-template', {
                'schemaVersion':'document-evaluation-prompt-template.v0.1',
                'id':_identifier(template_id), 'revision':revision,
                'systemInstruction':system_instruction,
                'answerInstruction':answer_instruction,
                'evidenceFormat':'NUMBERED_CLAUSE_QUOTES',
                'maxEvidenceItems':max_evidence_items,
                'maxAnswerCharacters':max_answer_characters})

    def register_source_classification(self, actor, classification_id, revision,
                                       source_digest, classification,
                                       external_model_allowed, providers, regions,
                                       execution_zones):
        actor.require('source.classify')
        with self.tx():
            self._source_access(actor, source_digest)
            if (classification in {'CONFIDENTIAL', 'RESTRICTED'}
                    and external_model_allowed):
                raise Rejected('EVALUATION_CLASSIFICATION_UNSUPPORTED')
            if external_model_allowed and (not providers or not regions):
                raise Rejected('EVALUATION_EGRESS_POLICY_INVALID')
            return self._put(actor, 'document-source-classification', {
                'schemaVersion':'document-source-classification.v0.1',
                'id':_identifier(classification_id), 'revision':revision,
                'sourceDigest':source_digest, 'classification':classification,
                'externalModelAllowed':external_model_allowed,
                'allowedProviders':providers, 'allowedRegions':regions,
                'allowedExecutionZones':execution_zones})

    def create_evaluation_assignment(self, actor, assignment_id, revision,
                                     candidate_digest, test_set_digest,
                                     profile_digest, retrieval_digest,
                                     classification_digest, model_selection_digest,
                                     prompt_template_digest, context, expires_at):
        actor.require('evaluation.manage')
        if not hasattr(context, 'facts'):
            raise Rejected('TRUSTED_CONTEXT_REQUIRED')
        host = context.facts()
        created = _now()
        if _timestamp(expires_at) <= created:
            raise Rejected('EVALUATION_ASSIGNMENT_EXPIRED')
        with self.tx():
            candidate, _, _, index = self._document_parts(actor, candidate_digest)
            test_set = self._get(actor, test_set_digest, 'document-quality-test-set')
            self._get(actor, profile_digest, 'document-quality-profile')
            retrieval = self._get(actor, retrieval_digest, 'document-retrieval-evaluation')
            self._get(actor, prompt_template_digest,
                      'document-evaluation-prompt-template')
            classification = self._get(actor, classification_digest,
                                       'document-source-classification')
            expected = (candidate_digest, profile_digest, test_set_digest)
            if ((retrieval['candidateDigest'], retrieval['profileDigest'],
                 retrieval['testSetDigest']) != expected
                    or test_set['candidateDigest'] != candidate_digest
                    or classification['sourceDigest'] != index['sourceDigest']):
                raise Rejected('EVALUATION_ASSIGNMENT_MISMATCH')
            self._source_current(actor, index['sourceDigest'], context.business_date)
            cases = [item['caseId'] for item in test_set['testSet']['cases']]
            return self._put(actor, 'document-evaluation-assignment', {
                'schemaVersion':'document-evaluation-assignment.v0.1',
                'id':_identifier(assignment_id), 'revision':revision,
                'candidateDigest':candidate_digest, 'sourceDigest':index['sourceDigest'],
                'indexDigest':candidate['indexDigest'], 'testSetDigest':test_set_digest,
                'profileDigest':profile_digest,
                'retrievalEvaluationDigest':retrieval_digest,
                'classificationDigest':classification_digest,
                'modelSelectionDigest':model_selection_digest,
                'promptTemplateDigest':prompt_template_digest,
                'businessContext':host, 'caseIds':cases,
                'createdAt':created.isoformat(), 'expiresAt':expires_at,
                'state':'READY'})

    def issue_evaluation_lease(self, actor, lease_id, revision,
                               assignment_digest, principal, worker_identity,
                               worker_build_digest, expires_at, nonce):
        actor.require('evaluation.lease.issue')
        issued = _now()
        with self.tx():
            assignment = self._get(actor, assignment_digest,
                                   'document-evaluation-assignment')
            expiry = _timestamp(expires_at)
            if expiry <= issued or expiry > _timestamp(assignment['expiresAt']):
                raise Rejected('EVALUATION_LEASE_EXPIRED')
            return self._put(actor, 'knowledge-evaluation-lease', {
                'schemaVersion':'knowledge-evaluation-lease.v0.1',
                'id':_identifier(lease_id), 'revision':revision,
                'assignmentDigest':assignment_digest, 'tenant':actor.tenant,
                'principal':_identifier(principal),
                'workerIdentity':_identifier(worker_identity),
                'workerBuildDigest':worker_build_digest,
                'caseIds':assignment['caseIds'], 'maxCalls':len(assignment['caseIds']),
                'issuedAt':issued.isoformat(), 'expiresAt':expires_at,
                'nonce':_identifier(nonce),
                'operation':'evaluation.evidence.read'})

    def revoke_evaluation_lease(self, actor, lease_digest, revocation_id):
        actor.require('evaluation.lease.issue')
        with self.tx():
            self._get(actor, lease_digest, 'knowledge-evaluation-lease')
            return self._put(actor, 'knowledge-evaluation-lease-revocation', {
                'schemaVersion':'knowledge-evaluation-lease-revocation.v0.1',
                'id':_identifier(revocation_id), 'revision':1,
                'leaseDigest':lease_digest, 'revokedAt':_now().isoformat(),
                'authorityRef':actor.authority})

    def _evaluation_scope(self, actor, assignment_digest, lease_digest, case_id):
        assignment = self._get(actor, assignment_digest,
                               'document-evaluation-assignment')
        lease = self._get(actor, lease_digest, 'knowledge-evaluation-lease')
        if (lease['assignmentDigest'] != assignment_digest
                or lease['tenant'] != actor.tenant
                or lease['principal'] != actor.principal
                or lease['workerIdentity'] != actor.authority
                or case_id not in lease['caseIds']
                or case_id not in assignment['caseIds']):
            raise Rejected('EVALUATION_SCOPE_MISMATCH')
        if _timestamp(lease['expiresAt']) <= _now() or _timestamp(assignment['expiresAt']) <= _now():
            raise Rejected('EVALUATION_LEASE_EXPIRED')
        revoked = self.db.execute(
            "SELECT 1 FROM objects WHERE tenant=? AND kind=? "
            "AND json_extract(body,'$.leaseDigest')=?",
            (actor.tenant, 'knowledge-evaluation-lease-revocation', lease_digest)).fetchone()
        if revoked:
            raise Rejected('EVALUATION_LEASE_REVOKED')
        test_set = self._get(actor, assignment['testSetDigest'],
                             'document-quality-test-set')
        matches = [item for item in test_set['testSet']['cases']
                   if item['caseId'] == case_id]
        if len(matches) != 1:
            raise Rejected('EVALUATION_CASE_MISMATCH')
        return assignment, lease, matches[0]

    def query_document_candidate_for_evaluation(self, actor, assignment_digest,
                                                lease_digest, case_id, request_id,
                                                trace_id, client):
        actor.require('evaluation.execute')
        _identifier(request_id); _identifier(trace_id); _identifier(case_id)
        with self.tx():
            assignment, lease, case = self._evaluation_scope(
                actor, assignment_digest, lease_digest, case_id)
            prior = self.db.execute(
                "SELECT 1 FROM objects WHERE tenant=? AND kind=? "
                "AND json_extract(body,'$.leaseDigest')=? "
                "AND json_extract(body,'$.caseId')=?",
                (actor.tenant, 'document-candidate-query-receipt', lease_digest,
                 case_id)).fetchone()
            if prior:
                raise Rejected('EVALUATION_LEASE_REPLAYED')
            candidate, _, _, index = self._document_parts(
                actor, assignment['candidateDigest'])
            profile = self._get(actor, assignment['profileDigest'],
                                'document-quality-profile')
            context = assignment['businessContext']
            activation = self._source_current(actor, index['sourceDigest'],
                                              context['business_date'])
            policy = self._head(actor, 'policy', 'current')[1]
        evidence = self._retrieve(index, case['question'], client, profile)
        with self.tx():
            current, _, _ = self._evaluation_scope(
                actor, assignment_digest, lease_digest, case_id)
            self._source_current(actor, index['sourceDigest'],
                                 context['business_date'])
            if current != assignment:
                raise Rejected('EVALUATION_ASSIGNMENT_MISMATCH')
            if self.db.execute(
                    "SELECT 1 FROM objects WHERE tenant=? AND kind=? "
                    "AND json_extract(body,'$.leaseDigest')=? "
                    "AND json_extract(body,'$.caseId')=?",
                    (actor.tenant, 'document-candidate-query-receipt', lease_digest,
                     case_id)).fetchone():
                raise Rejected('EVALUATION_LEASE_REPLAYED')
            trace = {'question':case['question'], 'profileDigest':assignment['profileDigest'],
                     'evidence':evidence}
            receipt = {
                'schemaVersion':'document-candidate-query-receipt.v0.1',
                'assignmentDigest':assignment_digest, 'leaseDigest':lease_digest,
                'candidateDigest':assignment['candidateDigest'],
                'sourceDigest':assignment['sourceDigest'],
                'indexDigest':candidate['indexDigest'],
                'testSetDigest':assignment['testSetDigest'],
                'profileDigest':assignment['profileDigest'], 'caseId':case_id,
                'question':case['question'], 'requestId':request_id,
                'traceId':trace_id, 'principal':actor.principal,
                'policyDigest':policy, 'sourceActivationDigest':activation,
                'businessContext':context,
                'result':{'decision':'EVIDENCE_FOUND' if evidence else 'EVIDENCE_NOT_FOUND',
                          'evidence':evidence},
                'retrievalTraceDigest':digest(trace), 'createdAt':_now().isoformat()}
            receipt_digest = self._put(actor, 'document-candidate-query-receipt', receipt)
        return {'receiptDigest':receipt_digest, **receipt}

    def register_model_gateway(self, actor, gateway_id, revision,
                               gateway_principal, build_digest, adapter_version,
                               deployments, receipt_authority,
                               qualification_digest):
        actor.require('model.gateway.manage')
        if not isinstance(deployments, list) or not deployments:
            raise Rejected('EVALUATION_MODEL_GATEWAY_INVALID')
        normalized = []
        for deployment in deployments:
            if not isinstance(deployment, dict) or set(deployment) != {
                    'id', 'provider', 'modelRef', 'modelConfigDigest',
                    'endpointOrigin', 'region', 'executionZone', 'external'}:
                raise Rejected('EVALUATION_MODEL_GATEWAY_INVALID')
            endpoint = _endpoint_origin(deployment['endpointOrigin'])
            if (type(deployment['external']) is not bool
                    or deployment['external'] != _endpoint_is_external(endpoint)):
                raise Rejected('EVALUATION_MODEL_ENDPOINT_CLASSIFICATION_MISMATCH')
            normalized.append({
                'id':_identifier(deployment['id']),
                'provider':_identifier(deployment['provider']),
                'modelRef':_identifier(deployment['modelRef']),
                'modelConfigDigest':deployment['modelConfigDigest'],
                'endpointOrigin':endpoint,
                'region':_identifier(deployment['region']),
                'executionZone':_identifier(deployment['executionZone']),
                'external':deployment['external'],
            })
        if len({item['id'] for item in normalized}) != len(normalized):
            raise Rejected('EVALUATION_MODEL_GATEWAY_INVALID')
        with self.tx():
            return self._put(actor, 'model-gateway-registration', {
                'schemaVersion':'model-gateway-registration.v0.1',
                'id':_identifier(gateway_id), 'revision':revision,
                'gatewayPrincipal':_identifier(gateway_principal),
                'buildDigest':build_digest, 'adapterVersion':adapter_version,
                'openJiuwenVersion':'0.1.17.post1',
                'deployments':normalized, 'receiptAuthority':receipt_authority,
                'qualificationDigest':qualification_digest, 'status':'QUALIFIED'})

    def authorize_model_egress(self, actor, authorization_id, revision,
                               assignment_digest, candidate_receipt_digest,
                               gateway_registration_digest, deployment_id,
                               purpose, redaction_profile, expires_at):
        actor.require('model.egress.authorize')
        issued = _now()
        with self.tx():
            assignment = self._get(actor, assignment_digest,
                                   'document-evaluation-assignment')
            receipt = self._get(actor, candidate_receipt_digest,
                                'document-candidate-query-receipt')
            classification = self._get(actor, assignment['classificationDigest'],
                                       'document-source-classification')
            gateway = self._get(actor, gateway_registration_digest,
                                'model-gateway-registration')
            deployments = [item for item in gateway['deployments']
                           if item['id'] == deployment_id]
            if len(deployments) != 1 or gateway['status'] != 'QUALIFIED':
                raise Rejected('EVALUATION_MODEL_GATEWAY_FORBIDDEN')
            deployment = deployments[0]
            if (receipt['assignmentDigest'] != assignment_digest
                    or receipt['sourceDigest'] != classification['sourceDigest']
                    or deployment['modelConfigDigest'] != assignment['modelSelectionDigest']):
                raise Rejected('EVALUATION_SCOPE_MISMATCH')
            if deployment['executionZone'] not in classification['allowedExecutionZones']:
                raise Rejected('EVALUATION_EGRESS_FORBIDDEN')
            if deployment['external'] and (not classification['externalModelAllowed']
                    or deployment['provider'] not in classification['allowedProviders']
                    or deployment['region'] not in classification['allowedRegions']):
                raise Rejected('EVALUATION_EGRESS_FORBIDDEN')
            if (classification['classification'] == 'RESTRICTED'
                    and deployment['external']):
                raise Rejected('EVALUATION_EGRESS_FORBIDDEN')
            if (_timestamp(expires_at) <= issued
                    or _timestamp(expires_at) > _timestamp(assignment['expiresAt'])):
                raise Rejected('EVALUATION_EGRESS_EXPIRED')
            evaluation_principal = Actor(actor.tenant, receipt['principal'],
                                         actor.authority)
            self._source_current(evaluation_principal, receipt['sourceDigest'],
                                 assignment['businessContext']['business_date'])
            evidence_digest = digest(receipt['result']['evidence'])
            return self._put(actor, 'model-egress-authorization', {
                'schemaVersion':'model-egress-authorization.v0.1',
                'id':_identifier(authorization_id), 'revision':revision,
                'assignmentDigest':assignment_digest, 'caseId':receipt['caseId'],
                'candidateReceiptDigest':candidate_receipt_digest,
                'classificationDigest':assignment['classificationDigest'],
                'promptDigest':assignment['promptTemplateDigest'],
                'evidenceDigest':evidence_digest,
                'gatewayRegistrationDigest':gateway_registration_digest,
                'deploymentId':deployment['id'], 'provider':deployment['provider'],
                'modelRef':deployment['modelRef'],
                'modelConfigDigest':deployment['modelConfigDigest'],
                'endpointOrigin':deployment['endpointOrigin'],
                'region':deployment['region'],
                'purpose':_identifier(purpose),
                'executionZone':deployment['executionZone'],
                'external':deployment['external'],
                'redactionProfile':_identifier(redaction_profile),
                'issuedAt':issued.isoformat(), 'expiresAt':expires_at,
                'decision':'ALLOW'})

    def _model_request_payload(self, actor, egress):
        receipt = self._get(actor, egress['candidateReceiptDigest'],
                            'document-candidate-query-receipt')
        assignment = self._get(actor, egress['assignmentDigest'],
                               'document-evaluation-assignment')
        template = self._get(actor, assignment['promptTemplateDigest'],
                             'document-evaluation-prompt-template')
        evidence = receipt['result']['evidence'][:template['maxEvidenceItems']]
        numbered = []
        for position, item in enumerate(evidence, 1):
            numbered.append(f"[{position}] {item['clause']}: {item['quote']}")
        user = (f"问题：{receipt['question']}\n\n已核验原文：\n"
                + ('\n'.join(numbered) if numbered else '未检索到可用原文')
                + f"\n\n{template['answerInstruction']}")
        payload = {'messages':[
            {'role':'system', 'content':template['systemInstruction']},
            {'role':'user', 'content':user}],
            'model':egress['modelRef'], 'temperature':0,
            'maxAnswerCharacters':template['maxAnswerCharacters']}
        return receipt, assignment, payload

    def prepare_model_invocation(self, actor, gateway_registration_digest,
                                 egress_authorization_digest, request_id,
                                 trace_id, runtime_identity):
        actor.require('model.receipt.record')
        _identifier(request_id); _identifier(trace_id)
        with self.tx():
            gateway = self._get(actor, gateway_registration_digest,
                                'model-gateway-registration')
            egress = self._get(actor, egress_authorization_digest,
                               'model-egress-authorization')
            deployments = [item for item in gateway['deployments']
                           if item['id'] == egress['deploymentId']]
            if (gateway['gatewayPrincipal'] != actor.principal
                    or gateway['receiptAuthority'] != actor.authority
                    or gateway['status'] != 'QUALIFIED'
                    or egress['gatewayRegistrationDigest'] != gateway_registration_digest
                    or len(deployments) != 1):
                raise Rejected('EVALUATION_MODEL_GATEWAY_FORBIDDEN')
            deployment = deployments[0]
            expected_identity = {**deployment,
                'gatewayBuildDigest':gateway['buildDigest'],
                'adapterVersion':gateway['adapterVersion'],
                'openJiuwenVersion':gateway['openJiuwenVersion'],
                'qualificationDigest':gateway['qualificationDigest']}
            if runtime_identity != expected_identity:
                raise Rejected('EVALUATION_MODEL_ENDPOINT_MISMATCH')
            if (_timestamp(egress['expiresAt']) <= _now()
                    or egress['decision'] != 'ALLOW'):
                raise Rejected('EVALUATION_EGRESS_EXPIRED')
            receipt, assignment, payload = self._model_request_payload(actor, egress)
            if (egress['promptDigest'] != assignment['promptTemplateDigest']
                    or egress['evidenceDigest'] != digest(receipt['result']['evidence'])):
                raise Rejected('EVALUATION_MODEL_REQUEST_MISMATCH')
            evaluation_principal = Actor(actor.tenant, receipt['principal'],
                                         actor.authority)
            self._source_current(evaluation_principal, receipt['sourceDigest'],
                                 assignment['businessContext']['business_date'])
            if self.db.execute(
                    "SELECT 1 FROM objects WHERE tenant=? AND kind=? "
                    "AND json_extract(body,'$.egressAuthorizationDigest')=?",
                    (actor.tenant, 'model-invocation-attempt',
                     egress_authorization_digest)).fetchone():
                raise Rejected('EVALUATION_MODEL_INVOCATION_REPLAYED')
            payload_digest = digest(payload)
            attempt = self._put(actor, 'model-invocation-attempt', {
                'schemaVersion':'model-invocation-attempt.v0.1',
                'egressAuthorizationDigest':egress_authorization_digest,
                'gatewayRegistrationDigest':gateway_registration_digest,
                'deploymentId':egress['deploymentId'], 'requestId':request_id,
                'traceId':trace_id, 'requestPayloadDigest':payload_digest,
                'runtimeIdentity':runtime_identity, 'createdAt':_now().isoformat()})
            return {'invocationAttemptDigest':attempt,
                    'requestPayloadDigest':payload_digest, **payload}

    def record_model_invocation(self, actor, gateway_registration_digest,
                                egress_authorization_digest, invocation_attempt_digest,
                                started_at, ended_at, outcome, response,
                                provider_request_ref, usage):
        actor.require('model.receipt.record')
        with self.tx():
            gateway = self._get(actor, gateway_registration_digest,
                                'model-gateway-registration')
            egress = self._get(actor, egress_authorization_digest,
                               'model-egress-authorization')
            attempt = self._get(actor, invocation_attempt_digest,
                                'model-invocation-attempt')
            deployments = [item for item in gateway['deployments']
                           if item['id'] == egress['deploymentId']]
            if (gateway['gatewayPrincipal'] != actor.principal
                    or gateway['receiptAuthority'] != actor.authority
                    or gateway['status'] != 'QUALIFIED'
                    or egress['gatewayRegistrationDigest'] != gateway_registration_digest
                    or len(deployments) != 1
                    or attempt['egressAuthorizationDigest'] != egress_authorization_digest
                    or attempt['gatewayRegistrationDigest'] != gateway_registration_digest
                    or attempt['deploymentId'] != egress['deploymentId']):
                raise Rejected('EVALUATION_MODEL_GATEWAY_FORBIDDEN')
            _, _, payload = self._model_request_payload(actor, egress)
            if attempt['requestPayloadDigest'] != digest(payload):
                raise Rejected('EVALUATION_MODEL_REQUEST_MISMATCH')
            if self.db.execute(
                    "SELECT 1 FROM objects WHERE tenant=? AND kind=? "
                    "AND json_extract(body,'$.invocationAttemptDigest')=?",
                    (actor.tenant, 'model-invocation-receipt',
                     invocation_attempt_digest)).fetchone():
                raise Rejected('EVALUATION_MODEL_INVOCATION_REPLAYED')
            started, ended = _timestamp(started_at), _timestamp(ended_at)
            if ended < started:
                raise Rejected('EVALUATION_TIME_INVALID')
            if (outcome == 'RETURNED'
                    and (not isinstance(response, str) or not response.strip()
                         or len(response) > 100000)):
                raise Rejected('EVALUATION_MODEL_RESPONSE_INVALID')
            if outcome == 'FAILED' and response is not None:
                raise Rejected('EVALUATION_MODEL_RESPONSE_INVALID')
            archive_digest = response_digest = None
            if outcome == 'RETURNED':
                response_digest = text_digest(response)
                archive_digest = self._put(actor, 'model-answer-archive', {
                    'schemaVersion':'model-answer-archive.v0.1',
                    'id':attempt['requestId'], 'revision':1,
                    'assignmentDigest':egress['assignmentDigest'],
                    'caseId':egress['caseId'], 'requestId':attempt['requestId'],
                    'traceId':attempt['traceId'], 'response':response,
                    'responseDigest':response_digest, 'createdAt':ended_at})
            receipt = {
                'schemaVersion':'model-invocation-receipt.v0.1',
                'assignmentDigest':egress['assignmentDigest'],
                'caseId':egress['caseId'],
                'egressAuthorizationDigest':egress_authorization_digest,
                'invocationAttemptDigest':invocation_attempt_digest,
                'gatewayRegistrationDigest':gateway_registration_digest,
                'gatewayPrincipal':actor.principal, 'provider':egress['provider'],
                'modelRef':egress['modelRef'],
                'modelConfigDigest':egress['modelConfigDigest'],
                'endpointOrigin':egress['endpointOrigin'],
                'external':egress['external'],
                'promptDigest':egress['promptDigest'],
                'evidenceDigest':egress['evidenceDigest'],
                'requestPayloadDigest':attempt['requestPayloadDigest'],
                'requestId':attempt['requestId'], 'traceId':attempt['traceId'],
                'startedAt':started_at, 'endedAt':ended_at, 'outcome':outcome,
                'answerArchiveDigest':archive_digest, 'responseDigest':response_digest,
                'providerRequestRef':provider_request_ref, 'usage':usage}
            return self._put(actor, 'model-invocation-receipt', receipt)

    def register_factory_evaluation_runtime_evidence(
            self, actor, assignment_digest, lease_digest, worker_build_digest,
            python_version, openjiuwen_version, runs):
        actor.require('candidate.validate')
        with self.tx():
            assignment = self._get(actor, assignment_digest,
                                   'document-evaluation-assignment')
            lease = self._get(actor, lease_digest, 'knowledge-evaluation-lease')
            if (lease['assignmentDigest'] != assignment_digest
                    or lease['tenant'] != actor.tenant
                    or lease['workerBuildDigest'] != worker_build_digest
                    or set(lease['caseIds']) != set(assignment['caseIds'])):
                raise Rejected('QUALITY_RUNTIME_BINDING_MISMATCH')
            if (_timestamp(lease['expiresAt']) <= _now()
                    or _timestamp(assignment['expiresAt']) <= _now()):
                raise Rejected('EVALUATION_LEASE_EXPIRED')
            if self.db.execute(
                    "SELECT 1 FROM objects WHERE tenant=? AND kind=? "
                    "AND json_extract(body,'$.leaseDigest')=?",
                    (actor.tenant, 'knowledge-evaluation-lease-revocation',
                     lease_digest)).fetchone():
                raise Rejected('EVALUATION_LEASE_REVOKED')
            by_id = {item.get('caseId'):item for item in runs if isinstance(item, dict)}
            if set(by_id) != set(assignment['caseIds']) or len(by_id) != len(runs):
                raise Rejected('QUALITY_RUNTIME_CASE_MISMATCH')
            cases, model_identity = [], None
            for case_id in assignment['caseIds']:
                run = by_id[case_id]
                candidate_receipt_digest = run.get('candidateReceiptDigest')
                model_receipt_digest = run.get('modelReceiptDigest')
                candidate_receipt = self._get(actor, candidate_receipt_digest,
                                              'document-candidate-query-receipt')
                model_receipt = self._get(actor, model_receipt_digest,
                                          'model-invocation-receipt')
                egress = self._get(actor, model_receipt['egressAuthorizationDigest'],
                                   'model-egress-authorization')
                attempt = self._get(actor, model_receipt['invocationAttemptDigest'],
                                    'model-invocation-attempt')
                evaluation_principal = Actor(
                    actor.tenant, candidate_receipt['principal'], actor.authority)
                self._source_current(
                    evaluation_principal, candidate_receipt['sourceDigest'],
                    assignment['businessContext']['business_date'])
                if (candidate_receipt['assignmentDigest'] != assignment_digest
                        or candidate_receipt['leaseDigest'] != lease_digest
                        or candidate_receipt['caseId'] != case_id
                        or model_receipt['assignmentDigest'] != assignment_digest
                        or model_receipt['caseId'] != case_id
                        or model_receipt['outcome'] != 'RETURNED'
                        or attempt['egressAuthorizationDigest']
                        != model_receipt['egressAuthorizationDigest']
                        or attempt['requestId'] != model_receipt['requestId']
                        or attempt['traceId'] != model_receipt['traceId']
                        or egress['candidateReceiptDigest'] != candidate_receipt_digest
                        or egress['evidenceDigest'] != digest(candidate_receipt['result']['evidence'])
                        or not model_receipt['answerArchiveDigest']):
                    raise Rejected('QUALITY_RUNTIME_RECEIPT_MISMATCH', case_id)
                archive = self._get(actor, model_receipt['answerArchiveDigest'],
                                    'model-answer-archive')
                if (archive['responseDigest'] != model_receipt['responseDigest']
                        or archive['responseDigest'] != text_digest(archive['response'])
                        or archive['assignmentDigest'] != assignment_digest
                        or archive['caseId'] != case_id
                        or archive['requestId'] != model_receipt['requestId']
                        or archive['traceId'] != model_receipt['traceId']):
                    raise Rejected('QUALITY_RUNTIME_MODEL_EVIDENCE_MISSING', case_id)
                identity = {'provider':model_receipt['provider'],
                            'modelRef':model_receipt['modelRef'],
                            'configVersion':model_receipt['modelConfigDigest']}
                model_identity = identity if model_identity is None else model_identity
                if identity != model_identity:
                    raise Rejected('QUALITY_RUNTIME_MODEL_INVALID')
                retrieved = []
                for evidence in candidate_receipt['result']['evidence']:
                    body = {'candidateReceiptDigest':candidate_receipt_digest,
                            'clause':evidence.get('clause'),
                            'quote':evidence.get('quote'),
                            'quoteDigest':text_digest(evidence.get('quote', '')),
                            'sourceDigest':candidate_receipt['sourceDigest'],
                            'originalDigest':evidence.get('originalDigest'),
                            'chunkId':evidence.get('chunkId')}
                    if any(not isinstance(value, str) or not value for value in body.values()):
                        raise Rejected('QUALITY_RUNTIME_EVIDENCE_MISMATCH', case_id)
                    body['evidenceDigest'] = digest(body)
                    retrieved.append(body)
                answer_citations, unmatched = self._factory_answer_references(
                    archive['response'], retrieved)
                cases.append({'caseId':case_id, 'answer':archive['response'],
                    'answerDigest':archive['responseDigest'],
                    'retrievedEvidence':retrieved, 'answerCitations':answer_citations,
                    'unmatchedAnswerCitations':unmatched,
                    'citedClauses':[item['clause'] for item in answer_citations],
                    'requestId':model_receipt['requestId'],
                    'traceId':model_receipt['traceId'],
                    'candidateReceiptDigest':candidate_receipt_digest,
                    'modelReceiptDigest':model_receipt_digest})
            body = {'schemaVersion':'document-factory-evaluation-runtime-evidence.v0.1',
                    'candidateDigest':assignment['candidateDigest'],
                    'testSetDigest':assignment['testSetDigest'],
                    'assignmentDigest':assignment_digest, 'leaseDigest':lease_digest,
                    'workerBuildDigest':worker_build_digest,
                    'pythonVersion':python_version,
                    'openJiuwenVersion':openjiuwen_version,
                    'modelIdentity':model_identity, 'cases':cases,
                    'verification':'CORE_CORRELATED_FACTORY_WORKER',
                    'createdAt':_now().isoformat()}
            return self._put(actor, 'document-factory-evaluation-runtime-evidence', body)
