# H1a consumption contract freeze candidate

This records the existing v0.1 wire protocol, not a new authority service.
Factory baseline: `2c40495a223f8cd1ec4f85aff3168d9e4491bc8e`.
Harness wire implementation inspected read-only at
`3dacab04e2a4a4f58baa48177c0cdf5a31a5415d` (PR 96).
No Harness/Builder files were changed. Cross-team acknowledgement and an actual
installed-Agent joint run remain pending; this is not a claim of mutual acceptance.

## Fixed instance

- Product: `run-39d069d400924257a857cfa7ec64917b`.
- Manifest: `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
- Producer: `c2939742f211a1ed363dc792d3602d0098765a04`.
- Service: loopback only, proposed port 61357. Port 61353 is forbidden by the
  new service entrypoint. No proxy, public port, background service installation,
  publication route or lease-issuance route is provided.
- `h1a-binding.json` pins product/Manifest independently of mutable Host files.

`knowledge-runtime-v0.1.schema.json` supplies executable request/response checks.
Its byte SHA-256 is returned in private process readiness/stop records. Both sides
should record that hash and their exact implementation commits before joint testing.

## POST /session

Exactly one `Authorization: Bearer <Host session credential>` header and a JSON
body of `{}`. There is no identity issuance, retrieval or durable grant here.

Success is HTTP 200 with exactly:

```json
{
  "code": 0,
  "schemaVersion": "knowledge-session-check.v0.1",
  "sessionRef": "host-issued-session",
  "productId": "run-39d069d400924257a857cfa7ec64917b",
  "manifest": "8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3"
}
```

The response has no requestId, traceId or Core receipt. It is a point-in-time
authorization check, not a reusable permission result. Host must still perform
its current-session checks before model execution and before disclosing results.

## POST /query

Same authentication. Exact fields:

```json
{
  "schemaVersion": "knowledge-query.v0.1",
  "capabilityId": "knowledge.evidence.search",
  "productId": "run-39d069d400924257a857cfa7ec64917b",
  "manifest": "8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3",
  "businessDate": "2026-10-30",
  "principalId": "knowledge-agent",
  "subjectRef": "host-issued-subject",
  "sessionRef": "host-issued-session",
  "purpose": "evidence-query",
  "requestId": "request-unique-id",
  "traceId": "trace-id",
  "arguments": {"question": "What does the source say?"}
}
```

Example identity/date values are NOT client authority. All must match the private
Host lease and its trusted context. Tenant, region, institution, product scope and
business-date provenance come only from that context. Only the question is Agent
input. No rules capability, endpoint override, grant, scope or version selector.

Success: HTTP 200, integer code 0, decision `EVIDENCE_FOUND` or `UNKNOWN`, evidence
array, and `knowledge-receipt.v0.1` receipt. Evidence carries clause, quote,
originalDigest, chunkId, original HTML anchors and Core sourceDigest.
An empty verified evidence set is UNKNOWN, not an affirmative business conclusion.

Correlation is:

1. Host sessionRef + original query requestId/traceId identify the tool invocation.
2. Receipt echoes requestId/traceId/productId/Manifest/businessDate and fixes source,
   index, binding and policy digests. `receiptId = "kr-" + coreReceiptDigest`.
3. Core's immutable document receipt contains the saved request, principal, trusted
   context and result; replay is permission checked and performs no retrieval.

The existing receipt does **not** contain sessionRef. Do not invent this field or
claim Core alone archives the full Host session/instance/Installation Lock chain.
Host must persist its invocation-to-session/Lock association. Repeated request IDs
are not an idempotency guarantee; QUERY has no financial write, but can append a
new audit receipt and perform another retrieval.

## Errors and bounds

Preserve baseline semantics: Rejected => HTTP 403 with `{code:403,error:CODE}`,
including `RAGFLOW_BUSINESS_ERROR` / `RAGFLOW_UNAVAILABLE`. This compatibility
choice does not mean every 403 is an authorization failure. Classify by error code;
do not silently change status mapping in either repository. Invalid HTTP/JSON
framing => 400; unknown route => 404; unexpected failures/overload => 503.
Denials have no evidence or success receipt. Transport records correlate denials
with the originating request; do not manufacture a Core success receipt.

One Content-Length, JSON only, no transfer encoding, max request 16 KiB, strict
duplicate-key/non-finite-number rejection, 5-second socket timeout. Successful
responses are capped at 256 KiB, matching the existing Java Provider bound.
RAGFlow's existing request timeout remains 60 seconds; Host's own configured
timeout still applies and may reject sooner. No retry or cached-success fallback.

## Private Host boundary, unchanged

Host/operator supplies `knowledge-host-authority.v0.1` policy and Host alone issues
`knowledge-host-lease.v0.1` files. Runtime reads both via existing `HostLeases`.
Policy and lease files must be regular, non-symlink, current-UID owned, mode 0600;
the absolute lease directory is mode 0700 and current-UID owned. Max file 16 KiB.
This isolated same-UID filesystem trust is **not production IAM or tenant isolation**.

Policy fields: schemaVersion, enabled, ownerRef, principalId, tenant, authority,
subjectRef, productId, manifest, context, expiresAt, leaseDirectory. Context uses
the existing BusinessContext keys: business_date, region, institution, product,
purpose, source, timezone. No privileges are constructed.

Lease filename is SHA-256(credential UTF-8) + `.json`; contents are schemaVersion,
policyDigest (exact policy bytes), ownerRef, instanceId, sessionRef, expiresAt.
The raw bearer is not written by Factory. Host bounds expiry, holds the bearer,
and deletes its lease on close. A policy change invalidates old policy-digest
leases. Runtime rejects missing/expired/revoked files and context mismatches.

Factory never activates a source, changes Core grants, publishes a Manifest or
creates a Host lease. Its checks happen before upstream client initialization,
after retrieval inside Core, and again after final Host session resolution.
Receipt storage before a final denial is possible; a stored internal receipt is
not proof of disclosure. Revocation after the final check cannot recall bytes
already delivered, so Host also checks before user-visible output.

## Joint handoff checklist

- Both teams acknowledge this wire schema hash and pin their commits.
- Harness supplies the private policy/lease path, actual runtime UID, and bound
  business date; Factory must not mint replacement sessions to make a build pass.
- Use a fresh isolated copy of the fixed Core snapshot, not the negative-test copy
  whose source has deliberately been revoked. The copy's current policy is checked;
  later permission changes in preview 61353 are not automatically mirrored.
- Harness still proves Builder admission, qualified collectors, Installation Lock,
  Agent UI query, denial, stop and history on one installation. This service's
  process-stop receipt proves only its own HTTP workers joined, not Agent/OS cleanup.
