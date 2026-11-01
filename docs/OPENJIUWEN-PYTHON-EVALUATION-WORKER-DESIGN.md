# OpenJiuwen Python Evaluation Worker: minimum design

## Decision and scope

Add one isolated Python 3.12 worker inside the Knowledge Factory trust boundary to
execute answer-quality evaluations. The worker is not an Agent product, an Agent
platform, a publication authority, or a replacement for Core.

This design PR contains no runtime implementation. A later implementation PR may
add the worker only after PR #11's quality contracts and immutable publication
admission are available on `main`.

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
3. For each frozen case, the worker asks Core for authorized evidence. Core runs
   the existing pinned query path and returns a normal receipt plus evidence.
4. The worker gives OpenJiuwen the frozen question and receipt-backed evidence.
   The model has no other tools and cannot select a source, Manifest, identity, or
   business date.
5. The worker records the unmodified answer, model attempt events, evidence receipt
   digests, timing, and failures, then submits one immutable execution bundle.
6. Core independently verifies the assignment, lease, receipts, model/runtime
   identity, and answer archive. Core derives answer citations and fact support,
   computes metrics, and decides quality admission using PR #11 contracts.
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
- allowed operation: `evaluation.evidence.read` only.

The browser, model, and worker request body cannot override these fields.

### `document-evaluation-execution.v0.1`

Worker-submitted raw evidence:

- assignment and lease digests;
- worker build SHA, Python version, OpenJiuwen SDK version, process/runtime identity;
- model reference and configuration digest, prompt-template digest;
- per-case request/trace IDs, Core receipt digests, original answer and answer digest;
- model attempt events, start/end timestamps, outcome and bounded error details;
- an idempotency key derived from assignment and worker attempt.

The record cannot contain caller-computed metrics, citation decisions, admission,
or a trusted execution label.

## OpenJiuwen and model adapter

- Run in a dedicated Python 3.12 virtual environment or container with an exact
  lockfile. Do not install packages into Knowledge Core's environment.
- Pin the OpenJiuwen Python SDK and adapter versions in the worker build record.
- Resolve model credentials by a host-owned configuration reference. Inject
  secrets at runtime; never persist them in assignments, evidence, logs, or Core.
- Permit only the evidence-read tool. Disable arbitrary filesystem, shell, network,
  and user-provided tools.
- Require structured completion containing answer text and cited evidence IDs, but
  preserve the provider's raw returned answer for Core verification.
- Bound concurrency, retries, response size, and per-case timeout. A retry creates a
  separate attempt and cannot overwrite a prior attempt.

## Core trusted acceptance

Core accepts an execution bundle only when all of the following hold:

- assignment and lease are valid, unexpired, single-tenant, and unused;
- candidate, source, index, test set, retrieval profile, and retrieval evaluation
  exactly match the assignment;
- every evidence item belongs to a verified Core receipt produced for that case;
- model selection, prompt, worker build, and runtime identities are complete;
- the original answers and model-attempt events have matching request/trace IDs;
- all configured cases are present exactly once, within size limits.

Core then creates the trusted runtime-evidence and answer-evaluation objects defined
by PR #11. It derives `retrievedEvidence`, `answerCitations`, unmatched citations,
fact support, forbidden-claim checks, metrics, and admission itself. A worker claim
such as `REAL_HARNESS_DEEPSEEK`, `VERIFIED`, or `PASS` has no authority.

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

The worker only replaces the manually orchestrated model-execution step. It does
not alter gold cases, thresholds, retrieval behavior, publication policy, or the
external `document-manifest.v0.1` contract. Existing products and historical
evidence remain byte-identical and readable without the worker.

## Failure behavior

Minimum stable failures for the implementation review:

- `EVALUATION_ASSIGNMENT_NOT_FOUND`;
- `EVALUATION_LEASE_INVALID`, `EVALUATION_LEASE_EXPIRED`,
  `EVALUATION_LEASE_REPLAYED`;
- `EVALUATION_SCOPE_MISMATCH` and `EVALUATION_SOURCE_FORBIDDEN`;
- `EVALUATION_RECEIPT_MISMATCH`;
- `EVALUATION_MODEL_UNAVAILABLE` and `EVALUATION_MODEL_RESPONSE_INVALID`;
- `EVALUATION_EXECUTION_INCOMPLETE`;
- `EVALUATION_EVIDENCE_REJECTED`.

Failure never creates a PASS admission or publishes a product. Partial answers and
attempt evidence are retained for diagnosis subject to the same access policy.

## Minimum implementation acceptance

The first implementation PR is complete only when it demonstrates:

1. an isolated Python 3.12 environment with pinned OpenJiuwen and model adapter;
2. one Core-authorized frozen candidate/test-set execution against the existing
   approved DeepSeek configuration, without reading secrets or Core storage;
3. exact original answers, Core receipt correlation, and Core-derived quality
   evaluation and admission;
4. rejection of expired lease, cross-tenant request, source revocation, receipt
   mismatch, missing case, fabricated citation, and conflicting replay;
5. model outage produces retained failure evidence and no admission;
6. existing Core, publication, query, authorization, and history regressions pass;
7. no Harness dependency and no workbench or publication UI changes.

Factory workbench scheduling, progress display, and publish controls belong to a
later, separate PR after this worker and Core acceptance path are reviewed.
