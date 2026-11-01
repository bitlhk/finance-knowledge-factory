"""No-agent orchestration for candidate evidence and model invocation."""
from uuid import uuid4


class CandidateEvaluationWorker:
    def __init__(self, core, actor, gateway, evidence_client,
                 authorize_model):
        self.core = core
        self.actor = actor
        self.gateway = gateway
        self.evidence_client = evidence_client
        self.authorize_model = authorize_model

    async def run(self, assignment_digest, lease_digest, case_ids):
        runs = []
        for case_id in case_ids:
            suffix = uuid4().hex
            candidate = self.core.query_document_candidate_for_evaluation(
                self.actor, assignment_digest, lease_digest, case_id,
                f"candidate-{suffix}", f"trace-{suffix}", self.evidence_client)
            authorization = self.authorize_model(candidate)
            model_receipt = await self.gateway.invoke(
                authorization, f"model-{suffix}", f"trace-{suffix}")
            runs.append({"caseId":case_id,
                         "candidateReceiptDigest":candidate["receiptDigest"],
                         "modelReceiptDigest":model_receipt})
        return runs
