# H1a stopped-Agent knowledge history: protocol proposal

Status: **PROPOSED / AWAITING HARNESS ACKNOWLEDGEMENT**. No HTTP implementation,
new authority files, running history service or endpoint acceptance is claimed.
User explicitly requires agreement before freezing/implementing this interface.

Factory baseline: `2a4a289`, executable Runtime baseline `705025a`.
Existing query/session wire schema remains byte-for-byte unchanged.
No Harness/Builder change, current Core grant/activation change or 61353 restart.

Candidate history schema SHA-256:
`114397ec532e40b84975e5884457ed1de63b45c71a05652c7e8ed5c3f1f3c3c6`.
Unchanged query/session schema SHA-256:
`ae9fa3dbf053829144983f3d23892eeef93d43e1a755f0306ccd0a01a209c4fa`.
These are proposal artifact identities, not proof of agreement or HTTP acceptance.

Local checks: 15 proposal shape tests passed; the complete suite passed 389 tests.
The initial full JUnit invocation emitted 12 existing record_property/xunit2 format
warnings, not failures. Results are under
`/home/ubuntu/outputs/knowledge-history-contract-proposal-20261031/`.
No history HTTP test, live RAGFlow call, model call or real Host issuance was run.

## Evidence and one identifier discrepancy

`/home/ubuntu/outputs/knowledge-h1a-closeout/joint-06/report.json` identifies:

- Agent/build: `agent-4aa7115b5b1e46eb`.
- Installed instance: `b611bd21-89e9-49da-88ad-57657c4b0fdf`.
- Manifest: `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
- Factory: `2a4a289f1276f916cef8522c8830f3f1857b29ce`.
- Existing history scope: `EXECUTION_METADATA_NOT_SAVED_ANSWER_BODY`.
- Model mode: `CONTROLLED_FIXTURE`; retrieval: real independent Factory service.

The new work order instead spells the Manifest with `...a90d5cdad624...`.
Both are valid 64-character strings, but different identities. The fixed binding
and joint report use `...a90d5dcad624...`. On 2026-10-31 (Asia/Shanghai), the user
confirmed the existing receipt value. No binding or saved receipt was changed.

The joint report is inspected historical evidence, not a new Agent rerun. No live
run-session credential or private Host policy was read for this proposal.

## Proposed wire contract

POST `/history/read`; schema `knowledge-history.v0.1`; JSON only. Bearer credentials
come from an independent trusted Host history-view authorization, never the old
Agent runtime session. Exact schemas are in
`contracts/runtime/knowledge-history-v0.1.proposed.schema.json`.

Request fields:

| Field | Meaning |
| --- | --- |
| schemaVersion | knowledge-history.v0.1 |
| requestId, traceId | This history-read attempt, not the original query |
| coreReceiptDigest | Exact content-addressed document receipt; no prefix |
| expected.productId, expected.manifest | Original saved product and Manifest |
| expected.sourceDigest, expected.sourceRevision | Original immutable source revision |
| expected.originalRequestId, expected.originalTraceId | Original query correlation |

No principal, tenant, role, permissions, current date, endpoint, session override
or wildcard receipt selector is accepted from the request body. `expected` fields
are integrity assertions, not authorization. Request IDs are correlation, not an
idempotency or authority grant. Repeated history reads do not execute anything.

Response fields: schemaVersion, code=0, replay=true, requestId/traceId echoing this
read, coreReceiptDigest, savedReceipt, queryResponse.

- `savedReceipt` is the exact stored document-receipt object, without the extra
  `receiptDigest`/`replay` wrapper that replay_document adds. Recompute its SHA-256
  with the existing Core canonical JSON (UTF-8, sorted keys, compact separators,
  unescaped Unicode, no floating-point values). It must equal coreReceiptDigest.
- `queryResponse` is the deterministic **projection of saved data** into the
  existing knowledge query response format, including original quotes/anchors and
  `knowledge-receipt.v0.1`. It is not a newly executed query or a claimed archived
  byte-for-byte HTTP response. Compare it structurally with the original captured
  response when that capture exists; never invent a capture that was not saved.
- `queryResponse.receipt.receiptId = "kr-" + coreReceiptDigest`; its requestId and
  traceId remain the original query IDs. New read IDs stay in the outer envelope.
- Source/index/Manifest/binding/policy digests in the original receipt remain
  historical values. Current permission checks do not rewrite them.
- No answer generation, RAGFlow call, model call or new query receipt. There is
  no saved Agent prose in Core; the API must not regenerate or claim to return it.

The proposal bundles the unchanged query schema definitions with local reference
prefixes. A test checks semantic equality with the existing schema; no network
schema fetch is permitted. The first shape test exposed a nested-URN resolution
failure in the pinned jsonschema version (13 passed, 1 failed). Local bundling
corrects the packaging without changing the old wire contract or loosening checks.

## Independent Host history authority, proposed for confirmation

Reuse the existing isolated Host private-file trust mechanism, but use separate
purpose-bound schemas/directories and a fresh credential, not a second identity
service. Host alone issues/revokes these files after checking current workbench
viewer identity and the requested stopped-Agent record. Factory only reads them.

`knowledge-history-authority.v0.1`: enabled, ownerRef, principalId, tenant,
authority, purpose=`knowledge.history.read`, productId, original manifest,
allowedReceiptDigests (explicit, no wildcard), expiresAt, leaseDirectory.

`knowledge-history-lease.v0.1`: policyDigest (exact policy-file bytes), ownerRef,
viewerSessionRef, expiresAt. File name SHA-256(bearer UTF-8) + `.json`.

Files are regular/non-symlink, same service UID, mode 0600, at most 16 KiB;
dedicated absolute history lease directory is same UID, mode 0700. Propose a
maximum 15-minute view lease, never extending the authority expiry. Host signs in
the viewer and holds the bearer; Factory writes no policy/lease or permission.
This is the current isolated filesystem trust boundary, not production IAM.

Even a live valid `knowledge-host-lease.v0.1` run credential is the wrong type for
history; stopped, revoked and expired run credentials cannot be renewed or reused
by this API. A history lease likewise cannot call `/query` or `/session`.

Host must map the requested receipt to its original Agent instance, Installation
Lock and saved invocation record before issuing history access. Core did not
store these Harness identifiers, so Factory cannot independently prove the Agent
association or infer it from a browser-provided agentId. No fake instance fields
are added to old receipts. Host returns user-visible history only after rechecking
its own current viewer authorization.

## Core checks and cross-principal decision requiring acknowledgement

1. Authenticate a current independent history lease; verify policy digest,
   expiry, viewer session, product/Manifest and exact receipt allow-list.
2. Call existing `DocumentCore.replay_document(actor,digest)` without privileges.
   It verifies content hash, current product history permission, current source
   read permission, and `receipt:<digest>/history` when principal differs.
3. Verify the immutable original Manifest, source revision, index, binding and
   saved evidence chain. Compare every expected field; never consult the active
   binding or require old sources still to be effective for new business use.
4. Recheck independent Host lease and replay permissions before returning; refuse
   if changed. Never expose partial evidence or leak whether an inaccessible
   receipt exists. Already-delivered bytes cannot be revoked retroactively.

Proposed cross-principal policy preserves Core semantics: another principal with
only product history + source read is denied. Delegated reading requires the
specific receipt history grant AND Host's explicit receipt allowance. No such
grant is created by Factory. Please confirm whether H1a should instead disallow
ALL cross-principal reads, even already explicitly granted ones; do not silently
choose between these policies. Default unauthorized cross-principal cases fail.

Historical source expiry/replacement differs from current source-read revocation:
the former may be viewed for audit, the latter must deny disclosure. Current
consume permission and a stopped run session are neither required nor sufficient
for history. Current history permission is always required.

## Error proposal (history route only)

| HTTP | error | Boundary |
| --- | --- | --- |
| 400 | HISTORY_REQUEST_INVALID | Invalid shape, digest syntax, duplicate keys or framing |
| 403 | HISTORY_AUTH_REQUIRED | Missing/wrong type/expired/revoked history authority |
| 403 | HISTORY_FORBIDDEN | Unallowed receipt, current rights denied or inaccessible/missing receipt; no existence disclosure |
| 409 | HISTORY_REFERENCE_MISMATCH | Authorized receipt disagrees with expected original references |
| 409 | HISTORY_INTEGRITY_FAILED | Authorized saved object/chain digest or evidence inconsistent |
| 413 | HISTORY_RESPONSE_LIMIT | Complete saved payload exceeds bound; never truncate to success |
| 503 | HISTORY_UNAVAILABLE | Storage/internal failure; no success fallback |

Error body exactly `{code: <HTTP code>, error: <code>}`, with no evidence or new
Core receipt. Caller associates the refusal with the originating read request.
The old query/session 403 mapping is not changed. Propose request <=16 KiB and
response <=512 KiB, allowing the original <=256 KiB query plus exact saved receipt;
Harness must confirm its history reader bound rather than reuse the query bound.

## Tests after agreement, not yet performed

Use an isolated backup containing the actual stopped-instance receipt, without
touching the original M2 or joint acceptance database. Copy hashes before/after.
Test good same-principal read; absent/expired/revoked/wrong-kind credentials;
source/history/receipt-level revocation before and during read; unprivileged
cross-principal, wrong expected references, missing/corrupted receipt; changed
active binding and historically inactive source. Preserve originals and failures.

Verify no execution by combining unreachable injected upstream plus fail-on-use
RAGFlow/model factories, observed outbound-call counters and unchanged count/hash
of every document-receipt before/after. Do not stop shared RAGFlow to simulate an
outage. Also run a history-only process with no upstream configuration; it should
read saved data without constructing a RAGFlow client. Report controlled isolation
separately from a real shared-service outage, which is not authorized here.

Proposed isolated history listener: `127.0.0.1:61358/history/read`; not running or
reserved yet. No runnable history startup command exists before implementation.
61353 stays on c293974; old `/query` and `/session` remain unchanged. PR 6 stays Draft.

## Required acknowledgement before freezing

Harness to confirm request/response shape, local schema hashes, independent Host
authorization lifecycle, cross-principal policy, response limit, and which saved
Core receipt belongs to the stopped instance. Then fix paired commits and implement
Factory only. A PR comment saying "proposal sent" is not acknowledgement or H1a
acceptance. Final same-instance UI/Lock/history proof remains the Harness task.
