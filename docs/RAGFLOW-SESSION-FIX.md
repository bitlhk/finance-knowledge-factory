# Bounded query-session fix, 2026-10-31

## Failure retained, attribution bounded

Harness `normal-build-08` remains a failed/partial real-model run. Its failed
request was `fh-request-554c9652-da7a-4577-aa05-dc04fc575781`; no old result,
observation or history archive was rewritten. A separate read-only diagnosis
records RAGFlow retrieval HTTP 401 at 03:06:54.237Z and Factory HTTP 403 observed
at 03:06:54.240916069Z. Core policy, binding and source activation did not change.
The Factory adapter maps an upstream HTTP error to RAGFLOW_UNAVAILABLE, then to
403 under the frozen protocol. The old Provider dropped the Factory error code.

Per-query logins and the reference RAGFlow implementation's token replacement
make session rotation a strong explanation, not a proven request-level diagnosis.
The original failed response body/upstream request association was not retained;
the inspected reference source was not independently matched to the binary.
This patch removes the observed per-process concurrency hazard without rewriting
the certainty of the original diagnosis or relaxing any refusal.

## Minimal implementation

`m2.product_service --mode query` now uses `RagflowQuerySession`:

- One lazy login per service lifetime; initialization is synchronized. Authorization
  admission still runs first. A failed initialization is not automatically retried.
- Each query owns a separate urllib opener and closeable transport. Only upstream
  connection/session metadata is reused; no result, Host lease or Core grant cache.
- Every query follows the existing Runtime admission and final Host/Core checks.
  Source revocation, product revocation and expired Host leases still fail closed.
- Upstream HTTP 401 invalidates this process's session. No login refresh, query
  retry or cached-success fallback. In-flight responses recheck session validity.
- Closing a query drops only its local token reference. Service shutdown joins
  workers, then drops the shared session token. HTTP error response bodies close.
- The query-session client rejects ingestion. Production/validation writers keep
  the existing explicit Ragflow lifecycle; they are not added to the query service.

Only the new generic query entrypoint changes session lifetime. Original H1a
entrypoints and existing 61353/public processes are not changed or restarted.
Query/session/history/discovery protocol files, Core grants and business rules
remain unchanged. No new Runtime or credential issuer is introduced.

## Evidence and limits

Implementation commit: `5f0bc7b` (full identity in native result).
Targeted HTTP/session/transport/product suite: **64 passed**. Full regression:
**312 passed**, including ten new session tests. Twelve existing pytest warnings
about record_property/xunit2 are preserved. Evidence is in
`evidence/product-session-fix/INDEX.json`; the original 302-test evidence is intact.
Native probe: one fixed batch of **two concurrent read-only RAGFlow retrievals**,
both successful, one login, zero automatic retries, zero generative model calls,
zero new Core query receipts. Original snapshot byte digest and release description
remain unchanged. The session closes and both worker futures finish.

The probe calls the actual retrieval adapter against the published index and
validates original evidence. It is not a Builder/Agent or Host-identity acceptance.
Controlled HTTP tests separately verify parallel Runtime requests, per-request
Host/Core permissions, final-check revocation, expired leases, terminal upstream
401 and failed login, isolated transports and shutdown behavior.

Process-local reuse does **not** coordinate another process logging into the same
upstream account. Such external rotation still fails closed; do not automatically
restart, refresh or weaken authorization to hide it. Shared deployment/session
ownership or a supported service credential would require a separately approved
change. No new credentials were created in this patch.

Cleanup evidence covers this probe's workers, HTTP response resources and local
session references. It is not global OS cleanup, upstream account logout, token
revocation or Agent resource-reclamation proof.

Harness must pin this new Factory candidate with its own fixed commits and rerun
the agreed ordinary Builder/page/query/stop/history path. H1b and final real-page
historical acceptance remain pending; two native retrievals do not close either.
