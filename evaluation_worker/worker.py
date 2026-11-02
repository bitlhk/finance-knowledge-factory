"""Narrow clients and fixed orchestration for candidate answer evaluation.

These interfaces reduce accidental authority in the Worker. They are not an
operating-system security boundary; production deployment must place Core and
the model gateway behind separately authenticated service interfaces.
"""
from uuid import uuid4


class CandidateQueryClient:
    """Core-owned client bound to one assignment, lease, and Worker actor."""

    def __init__(self, core, actor, assignment_digest, lease_digest,
                 evidence_client):
        self.__core = core
        self.__actor = actor
        self.__assignment = assignment_digest
        self.__lease = lease_digest
        self.__evidence_client = evidence_client

    def query(self, case_id, request_id, trace_id):
        return self.__core.query_document_candidate_for_evaluation(
            self.__actor, self.__assignment, self.__lease, case_id,
            request_id, trace_id, self.__evidence_client)


class ModelAuthorizationClient:
    """Host-owned client fixed to one qualified gateway deployment."""

    def __init__(self, core, actor, assignment_digest,
                 gateway_registration_digest, deployment_id, purpose,
                 redaction_profile, expires_at):
        self.__core = core
        self.__actor = actor
        self.__assignment = assignment_digest
        self.__gateway = gateway_registration_digest
        self.__deployment = deployment_id
        self.__purpose = purpose
        self.__redaction = redaction_profile
        self.__expires_at = expires_at

    def authorize(self, candidate_receipt):
        suffix = uuid4().hex
        return self.__core.authorize_model_egress(
            self.__actor, f"model-egress-{suffix}", 1, self.__assignment,
            candidate_receipt["receiptDigest"], self.__gateway,
            self.__deployment, self.__purpose, self.__redaction,
            self.__expires_at)


class CandidateEvaluationWorker:
    """Runs only candidate query, authorization, and trusted gateway invoke."""

    def __init__(self, query_client, authorization_client, gateway):
        self.__query_client = query_client
        self.__authorization_client = authorization_client
        self.__gateway = gateway

    async def run(self, case_ids):
        runs = []
        for case_id in case_ids:
            suffix = uuid4().hex
            candidate = self.__query_client.query(
                case_id, f"candidate-{suffix}", f"trace-{suffix}")
            authorization = self.__authorization_client.authorize(candidate)
            model_receipt = await self.__gateway.invoke(
                authorization, f"model-{suffix}", f"trace-{suffix}")
            runs.append({"caseId":case_id,
                         "candidateReceiptDigest":candidate["receiptDigest"],
                         "modelReceiptDigest":model_receipt})
        return runs
