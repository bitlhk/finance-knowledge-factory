# OpenJiuwen Python Evaluation Worker

## Implementation status

PR #12 now implements the reviewed minimum design on top of merged PR #11.
The implementation and real-model acceptance remain Draft and are not deployed.
The first complete path is covered: Core-authorized candidate retrieval, a real
OpenJiuwen/DeepSeek invocation, immutable gateway receipts, and Core-owned answer
evaluation and quality admission. See
`docs/OPENJIUWEN-PYTHON-EVALUATION-WORKER-ACCEPTANCE.md`.

## Decision and scope

Add one isolated Python 3.12 worker with OpenJiuwen `0.1.17.post1` inside the
Knowledge Factory trust boundary to
execute answer-quality evaluations. The worker is not an Agent product, an Agent
platform, a publication authority, or a replacement for Core.

PR #11's quality contracts and immutable publication admission are available on
`main`; this PR adds the Worker implementation without workbench or publication UI.

In scope:

- read an immutable candidate evaluation assignment authorized by Core;
- query candidate knowledge through an authorized, read-only Core interface;
- call one version-pinned OpenJiuwen Python model adapter;
- preserve the original model answer and execution events;
- submit raw execution evidence to Core for independent verification.

Out of scope:

- JiuwenSwarm or multi-Agent orchestration;
- a new Agent, workflow, or knowledge-query platform;
- changes to Finance Harness or Builder;
- Factory workbench controls, scheduling, or publication wiring;
- PDF/DOCX ingestion, retrieval tuning, or new quality thresholds;
- permission, source-activation, publication, or history-policy changes.

## Trust boundary

Core remains the sole authority for source access, candidate identity, frozen test
sets, evidence receipts, quality metrics, admission, and publication. The worker
must never read the Core database or RAGFlow directly.

The worker receives a short-lived, single-assignment lease minted by the trusted
Factory host. The host, not the caller or model, fixes:

- tenant and evaluation principal;
- candidate, source, index, test-set, and retrieval-profile digests;
- model reference and model-configuration digest;
- allowed read-only Core operation and expiry;
- assignment ID, request ID, and trace ID.

The lease cannot grant source access that the requesting evaluation authority does
not already have. Expired, replayed, cross-tenant, or digest-mismatched leases are
rejected before a model call.

## Minimum execution flow

1. Core creates an immutable evaluation assignment from exact candidate,
   test-set, retrieval-evaluation, model-selection, and prompt-template digests.
2. The host leases that assignment to one worker instance.
3. For each frozen case, the worker calls the candidate-only evidence endpoint.
   Core verifies the assignment lease, source access, and exact candidate versions,
   then runs the same retrieval and original-text validation functions used by the
   published path. It returns a candidate-query receipt, not a production receipt.
4. The worker asks the host-owned model gateway to invoke OpenJiuwen with the
   frozen question and receipt-backed evidence. The gateway first verifies an
   exact model-egress authorization and records the actual provider attempt.
   The model has no other tools and cannot select a source, Manifest, identity, or
   business date.
5. The worker submits the unmodified answer plus candidate-query and model-call
   receipt digests. It cannot create either receipt or declare that a call succeeded.
6. Core independently loads and verifies the assignment, lease, candidate-query
   receipts, model-call receipts, Worker/runtime identity, and answer archive. Core
   derives answer citations and fact support, computes metrics, and decides quality
   admission using a versioned Factory-evaluation evidence contract.
7. The worker acknowledges completion only after Core returns the accepted
   runtime-evidence digest. It never returns `PASS` on its own authority.

No-answer cases may receive background evidence. Core still rejects unsupported
affirmative claims and does not treat all retrieved evidence as answer citations.

## Proposed internal records

Names are provisional until implementation review. They are internal and do not
change the external document query, Manifest, authorization, or history contracts.

### `document-evaluation-assignment.v0.1`

Core-created immutable input:

- `assignmentId`, `candidateDigest`, `sourceDigest`, `indexDigest`;
- `testSetDigest`, `retrievalEvaluationDigest`, `profileDigest`;
- `modelSelectionDigest`, `promptTemplateDigest`;
- `createdAt`, `expiresAt`, `caseIds`.

### `knowledge-evaluation-lease.v0.1`

Host-signed execution authority:

- `leaseId`, `assignmentDigest`, `tenant`, `principal`;
- `workerIdentity`, `issuedAt`, `expiresAt`, `nonce`;
- frozen case IDs, maximum calls, and per-case request nonce policy;
- allowed operation: `evaluation.evidence.read` only.

The browser, model, and worker request body cannot override these fields.

### `document-candidate-query-receipt.v0.1`

Core-created receipt for one unpublished-candidate evaluation query:

- assignment, lease, candidate, source, index, test-set, and profile digests;
- case ID, exact frozen question digest, request ID, and trace ID;
- policy digest, source-access decision, source version and activation checked at
  execution time;
- selected evidence with original digest, exact anchors, clause IDs, chunk IDs,
  and retrieval trace digest;
- created time, expiry context, and decision.

This receipt is not a `document-receipt.v0.1`, does not name a Manifest or Binding,
and cannot authorize production query, publication, or history disclosure.

### `model-egress-authorization.v0.1`

Policy-authority decision fixed before each model invocation:

- assignment, candidate, source, case, evidence, and prompt digests;
- source classification and allowed execution zone;
- exact provider, model reference, configuration digest, region, and purpose;
- permitted fields/redaction profile, issued time, expiry, and decision.

No authorization means no model request. An authorization for an internal model
cannot be reused with an external provider.

### `model-gateway-registration.v0.1`

Core/host-managed qualification for the service that actually calls the model:

- gateway service identity, build digest, adapter and OpenJiuwen versions;
- permitted provider endpoint identities, regions, and model references;
- receipt-signing identity, qualification evidence digest, validity, and status.

The Worker can reference but cannot create or update this registration.

### `model-invocation-receipt.v0.1`

Created only by the host-owned model gateway after the actual provider attempt:

- assignment/case, egress-authorization, prompt, and evidence digests;
- gateway identity, provider endpoint identity, model reference/configuration,
  request ID, trace ID, start/end time, outcome, and bounded usage metadata;
- exact response digest and encrypted/archive reference for the original response;
- provider request correlation where available, without credentials or content logs.

The Worker cannot write this store or supply authoritative values for this record.
Core accepts the receipt only from a registered gateway service identity over an
authenticated service channel. Gateway registration pins its build, adapter,
permitted provider endpoints, receipt-signing identity, and qualification status.
Receipt signatures or MAC keys are unavailable to the Worker. A provider request
correlation value is supporting evidence, not a substitute for gateway identity.

### `document-factory-evaluation-runtime-evidence.v0.1`

Core-created trusted evidence after validating a Worker submission:

- assignment and lease digests;
- Worker build SHA, Python version, OpenJiuwen `0.1.17.post1`, and runtime identity;
- model reference and configuration digest, prompt-template digest;
- per-case candidate-query receipt and model-invocation receipt digests;
- original answer/archive digest, request/trace IDs, outcome, and bounded errors;
- verification value `CORE_CORRELATED_FACTORY_WORKER`;
- an idempotency key derived from assignment and Worker attempt.

The accepted record contains no Harness Build ID, Agent Instance ID, Installation
Lock, or stopped-instance receipt. Those fields belong only to the Harness archive
evidence contract and must not be synthesized for Factory execution.

## OpenJiuwen and model adapter

- Run in a dedicated Python 3.12 virtual environment or container with an exact
  lockfile. Do not install packages into Knowledge Core's environment.
- Pin OpenJiuwen to `0.1.17.post1` and pin the model adapter in the Worker build
  record. A different SDK requires a new qualified Worker build.
- Resolve model credentials by a host-owned configuration reference. Inject
  secrets at runtime; never persist them in assignments, evidence, logs, or Core.
- Permit only the evidence-read tool. Disable arbitrary filesystem, shell, network,
  and user-provided tools.
- Require structured completion containing answer text and cited evidence IDs, but
  preserve the provider's raw returned answer for Core verification.
- Bound concurrency, retries, response size, and per-case timeout. A retry creates a
  separate attempt and cannot overwrite a prior attempt.

## Candidate-only evidence query

An unpublished Candidate has no Manifest or Binding and therefore must not call or
impersonate `query_document()`. The implementation adds an internal Core operation,
provisionally `query_document_candidate_for_evaluation()`, with no browser route.

The operation requires both `candidate.evaluate` and
`candidate.evidence.read`. It accepts only an assignment digest, host-minted lease,
case ID, request ID, and trace ID. The question, candidate, source, index, test set,
and quality profile are loaded from the immutable assignment; callers cannot send
replacement values.

Core then:

1. verifies tenant, principal, lease scope/expiry, per-case nonce non-reuse, and
   assignment status;
2. rechecks current source access and activation for the evaluation principal;
3. verifies the exact Candidate, source, index, test-set, and profile digests;
4. reuses the production retrieval selection, indexed-chunk integrity, bridge,
   original-text digest, clause, and anchor validators;
5. writes `document-candidate-query-receipt.v0.1` before returning evidence.

The candidate receipt is immutable and version-pinned. Source or assignment
revocation blocks the next query immediately; lease revocation or expiry blocks the
remaining cases. Existing receipts remain audit records but do not grant continued
source disclosure. Any later receipt read requires its own current audit/history
authorization. Candidate receipts are rejected by production query and history
interfaces.

## Source classification and model egress

Every source version used for evaluation must carry a Core-controlled classification
and egress policy. The minimum classification set is `PUBLIC`, `INTERNAL`,
`CONFIDENTIAL`, and `RESTRICTED`; labels are policy inputs, not Worker metadata.

Before sending any text to a model, the model gateway requires a valid
`model-egress-authorization.v0.1` binding the exact source, evidence, prompt,
provider, model, region, purpose, and redaction profile. Recommended default policy:

- `PUBLIC`: an approved external or internal model may be allowed;
- `INTERNAL`: only explicitly approved provider/model/region combinations;
- `CONFIDENTIAL`: internal execution zone unless a specific exception authority is
  recorded for the exact assignment;
- `RESTRICTED`: no external-model egress.

The gateway rechecks authorization immediately before every case, sends only the
minimal receipt-backed evidence, and denies unknown fields. Revocation stops later
cases and retries. Negative tests must inspect the actual outbound request and prove
that unauthorized source text, tenant metadata, identities, and credentials are not
sent. Digests and bounded metadata may be logged; source or prompt content follows
the source's storage and audit policy.

## Core trusted acceptance

Core accepts an execution bundle only when all of the following hold:

- assignment and lease are valid, unexpired, single-tenant, and unused;
- candidate, source, index, test set, retrieval profile, and retrieval evaluation
  exactly match the assignment;
- every evidence item belongs to a candidate-query receipt produced for that case;
- every answer is bound to a model-invocation receipt created by the trusted model
  gateway under an exact, current egress authorization;
- model selection, prompt, Worker build, and runtime identities are complete;
- original answers, candidate receipts, and model receipts have matching
  assignment/case/request/trace IDs and response digests;
- all configured cases are present exactly once, within size limits.

PR #11's `document-answer-runtime-evidence.v0.1/v0.2` remains exclusively for
`CORE_CORRELATED_HARNESS_ARCHIVE`. Factory evaluation instead creates
`document-factory-evaluation-runtime-evidence.v0.1` with
`CORE_CORRELATED_FACTORY_WORKER`. Neither verifier accepts the other contract.

A versioned `document-answer-evaluation.v0.3` accepts one of those two verified
evidence kinds through explicit Core adapters:

- the Harness adapter requires real Build, Agent Instance, Installation Lock,
  runtime Lock, model events, Factory receipts, and stopped-instance correlation;
- the Factory adapter requires assignment/lease, Candidate receipts, Worker build,
  egress authorization, and model-gateway receipts, and forbids Harness identity
  fields.

Each adapter creates the same private `VerifiedAnswerCase` projection in memory.
Only that projection enters the existing fact, citation, forbidden-claim, metrics,
and quality-gate logic. The caller cannot submit this projection. Quality admission
records the answer-evaluation digest and thereby the exact evidence authority.
`document-quality-admission.v0.2` additionally records the Core-derived
`answerEvidenceAuthority` and `qualityGateVersion`. Its gate accepts only a verified
Harness adapter result or a verified Factory adapter result; metrics and thresholds
remain identical. A worker claim such as `REAL_HARNESS_DEEPSEEK`, `VERIFIED`, or
`PASS` has no authority.

The existing answer-evaluation versions and v0.1 admissions remain readable and
valid. `publish_quality_document()` accepts either a valid existing v0.1 admission
or a Core-computed v0.2 admission and pins its exact digest using PR #11's immutable
Manifest-admission link. No fallback converts legacy or unqualified execution
records into v0.3 evidence.

Acceptance is idempotent. Re-submission of the exact bundle returns the existing
digest; a conflicting bundle for the same attempt is rejected and retained as a
failed attempt record.

## Relationship to PR #11

The implementation depends on PR #11 for:

- frozen quality profile and test-set identities;
- retrieval and answer evaluation contracts;
- trustworthy separation of retrieved evidence and answer citations;
- Core-computed quality admission;
- immutable binding from a published Manifest to its exact admission.

The Worker only replaces the manually orchestrated model-execution step. It does
not alter gold cases, thresholds, retrieval behavior, publication policy, or the
external `document-manifest.v0.1` contract. Existing products and historical
evidence remain byte-identical and readable without the worker.

## Failure behavior

Minimum stable failures for the implementation review:

- `EVALUATION_ASSIGNMENT_NOT_FOUND`;
- `EVALUATION_LEASE_INVALID`, `EVALUATION_LEASE_EXPIRED`,
  `EVALUATION_LEASE_REPLAYED`;
- `EVALUATION_SCOPE_MISMATCH` and `EVALUATION_SOURCE_FORBIDDEN`;
- `EVALUATION_EGRESS_FORBIDDEN` and `EVALUATION_CLASSIFICATION_UNSUPPORTED`;
- `EVALUATION_RECEIPT_MISMATCH`;
- `EVALUATION_MODEL_RECEIPT_MISSING` and `EVALUATION_MODEL_RECEIPT_MISMATCH`;
- `EVALUATION_MODEL_UNAVAILABLE` and `EVALUATION_MODEL_RESPONSE_INVALID`;
- `EVALUATION_EXECUTION_INCOMPLETE`;
- `EVALUATION_EVIDENCE_REJECTED`.

Failure never creates a PASS admission or publishes a product. Partial answers and
attempt evidence are retained for diagnosis subject to the same access policy.

## Minimum implementation acceptance

The first implementation PR is complete only when it demonstrates:

1. an isolated Python 3.12 environment with OpenJiuwen `0.1.17.post1` and a pinned
   model adapter;
2. one Core-authorized frozen candidate/test-set execution against the existing
   approved DeepSeek configuration, without reading secrets or Core storage;
3. candidate-only queries produce candidate receipts and exercise the same indexed
   chunk, original text, clause, and anchor checks as published queries;
4. exact original answers, model-gateway receipts, Core receipt correlation, and
   Core-derived quality evaluation/admission with Factory evidence authority;
5. rejection of expired lease, cross-tenant request, source revocation, receipt
   mismatch, missing case, fabricated citation, and conflicting replay;
6. classification and egress tests prove restricted knowledge cannot reach an
   external model and inspect the actual outbound payload for forbidden fields;
7. a forged success without a model-gateway receipt is rejected; model outage
   produces retained failure evidence and no admission;
8. both qualified Harness and Factory evidence pass through separate adapters,
   while cross-kind or incomplete evidence is rejected;
9. existing Core, publication, query, authorization, and history regressions pass;
10. no Harness dependency and no workbench or publication UI changes.

Factory workbench scheduling, progress display, and publish controls belong to a
later, separate PR after this worker and Core acceptance path are reviewed.

## Remaining sequence after implementation review

1. Keep PR #12 Draft until the implementation and its retained success/failure
   evidence are reviewed.
2. Do not deploy PR #12 to the current Factory service before approval.
3. A later workbench PR may schedule evaluation and publication. Its end-to-end
   acceptance must prove that a Factory-evaluated and published product is returned
   by the existing Harness refresh interface, can be version-selected and built,
   and is consumed with source evidence. External Manifest, query, authorization,
   and stopped-history contracts must remain unchanged.
