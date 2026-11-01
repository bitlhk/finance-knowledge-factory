# Knowledge product delivery v0.1

Backend dependency: PR #8, `ed350496156070d6a271a03e6b217e1725623d44`.
This incremental Draft must not merge PR #7's overlapping A-C or its D page.
No public deployment, original data writes, rule/Wiki promotion or IAM issuance.

## Contracts and authority

`contracts/runtime/knowledge-products-v0.1.schema.json` defines the release
description, discovery request/response and private Host discovery authorization.
The query, session and history schemas remain byte-identical to PR #8.
Frozen discovery schema SHA-256:
`0b671ae3de0dcb04e0614a9bed80ee38b7cd4672fb9db9df064aabe25f0a7e4e`.
Harness thread `019ef935-6aac-72d1-bd18-4a13d8001606` ACKed this exact hash
on 2026-10-31 after requesting Builder-compatible connectionRef syntax and a
maximum 60-second response lifetime. The ACK is contract agreement, not joint
Builder/Agent acceptance.

`POST /products/discover` accepts only schemaVersion
`knowledge-products-discover.v0.1`, requestId and traceId. A separate Host-issued
Bearer discovery lease is mandatory. Factory checks its private authority and
lease on every request; it neither creates nor renews them. Agent runtime and
history tokens are not accepted as discovery credentials, or vice versa.

Host's `allowedProductIds` is the directory access limit, not a Core grant.
Only products also passing Core's current consume/source_read permission,
active binding, source validity and trusted BusinessContext are returned.
No identity, role, product filter, URL or business date is taken from the request.
Products outside this intersection, including revoked and unpublished products,
are omitted without revealing names or IDs. A successful empty list means no
eligible product, not a healthy upstream retrieval service. Corrupt release
metadata and operational errors fail the request, not silently return an empty list.

Published state belongs to the immutable Manifest; it is not overwritten on
revocation. Discovery is a current eligibility check, not permanent authorization.
Current policy changes are enforced again by query/session/history. No revocation
directory is exposed to a caller who no longer has metadata access.

Private Host policy: `knowledge-discovery-authority.v0.1`, enabled, ownerRef,
tenant, principalId, authority, allowedProductIds, trusted context, expiresAt,
leaseDirectory. Host lease: `knowledge-discovery-lease.v0.1`, ownerRef,
policyDigest (SHA-256 of exact private policy bytes), builderSessionRef, expiresAt.
Lease filename: SHA-256(Bearer UTF-8) + `.json`. Files must be absolute, non-symlink,
current service UID owned mode 0600; lease directory mode 0700. At most 15 minutes
remaining lease lifetime, bounded by authority expiry. Disabling authority or
removing a lease revokes discovery. This same-UID trust is an isolated integration
boundary, not production IAM. Ubuntu/root remain trusted operators.

`checkedAt` and `expiresAt` bound each response to at most 60 seconds, additionally
bounded by Host lease expiry. Builder must reject expired responses and recheck
at selection/build time. The deterministic release descriptor has no timestamp.

Request limit 16 KiB, complete response limit 512 KiB, no truncation. Error codes:
400 DISCOVERY_REQUEST_INVALID; 403 DISCOVERY_AUTH_REQUIRED;
409 DISCOVERY_INTEGRITY_FAILED; 413 DISCOVERY_RESPONSE_LIMIT;
503 DISCOVERY_UNAVAILABLE. Responses have Cache-Control: no-store. No bearer,
request body, private policy or knowledge content is logged.

## Builder selection and installation mapping

1. Authenticated Builder asks its Host for independent discovery authorization.
2. Call discovery from the server. Display product name/type/version and explicit
   `M2_ISOLATED_DOCUMENT`, `productionAuthorized=false`. Source title is untrusted
   display text: render as text, never HTML or model instructions.
3. Browser selects productId + version + manifestDigest only. Builder re-discovers
   server-side and requires an exact match. Never accept a browser descriptor,
   connection URL, permissions or forged digest as authority.
4. Pin descriptorDigest, productId, version, manifestDigest and connectionRef in
   the managed configuration/installation evidence. Descriptor digest is Core's
   canonical JSON SHA-256 (sorted keys, UTF-8, compact separators), not file hash.
5. Resolve connectionRef using the trusted Builder connection registry. It is a
   logical reference, not a reachable endpoint or credential. Query and history
   can have different loopback service addresses, both supplied by the operator.

| Release description | Existing consumption binding |
| --- | --- |
| productId | knowledge-runtime-binding.v0.1 productId; /query productId |
| manifestDigest | binding manifest; /query manifest; /history/read expected.manifest |
| version | human revision; not an alternate Manifest selector |
| descriptorDigest | managed configuration / Lock association; not a wire-field addition |
| connectionRef | trusted managed connection lookup; never model-controlled URL |
| capabilities | install only knowledge.evidence.search |
| applicability | all scopes must match Host context; never grant by scope declaration |
| permissions | requirements, not grants or intendedConsumers authority |

Runtime uses fresh independent Host credentials, subject/session, purpose and
business date. Discovery permission is neither Agent admission nor runtime grant.
History uses a fresh independent viewer authorization and the exact original
receipt; stopped Agent sessions do not suffice.

The release includes only evidence hashes/identifiers, not document text, chunks,
RAGFlow dataset IDs, credentials or user lists. Builder need not copy the knowledge.
Factory does not activate sources, approve candidates, mint identities or set Core
policy during discovery or consumption.

## Version and receipt semantics

An old PINNED Lock never follows a new version. If the active binding changes,
the old query fails MANIFEST_MISMATCH; explicit managed re-selection/install is
needed. Revoked source/consume permission refuses queries. Independently authorized
history can still read the saved old Manifest, but requires current history and
source_read rights and, for another principal, exact Host receipt permission AND
Core receipt-history permission. No re-query, model regeneration or new query receipt.

Query requestId/traceId echo in knowledge-receipt.v0.1; receiptId is `kr-` plus
coreReceiptDigest. Source ID/revision/digest, original anchors, index and Manifest
remain associated. Host archives its session, Agent instance and Installation Lock
association; Factory does not create Harness answer archives. A discovery response
has no Core query receipt and its requestId/traceId identify only metadata access.

## Fixed real isolated release

`examples/products/h1a-release.json` is exported read-only from the original M2
snapshot, not a newly granted or newly published fixture. Product:
`run-39d069d400924257a857cfa7ec64917b`, name `合成客服制度`, version 1.
Manifest: `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
Source producer `c2939742f211a1ed363dc792d3602d0098765a04`.
Connection reference `knowledge-factory-isolated` requires operator registration;
the description does not claim that Builder has already registered it.

Example question: `合成客服服务时间是什么？` Saved source clause states
`合成客服服务时间为每日09:00至17:00。` Other clauses concern synthetic statement
requests and manual checking when information is missing. This is synthetic test
content, never bank-approved policy. Context: CN-BJ / synthetic-bank /
customer-service / evidence-query, valid from 2026-01-01, Asia/Shanghai.

## Acceptance boundary

## Isolated startup

Use a fresh isolated database or read-consistent copy, never the original M2
database for query tests (queries append receipts). No service is installed or
started by importing these modules. `--port 0` obtains an unused loopback port;
the new exclusive readiness JSON records its address and code identity.

```bash
python -m m2.discovery_service --database /absolute/isolated/core.sqlite \
  --authority /absolute/host/discovery-authority.json \
  --connection-ref knowledge-factory-isolated --port 0 \
  --ready-file /absolute/new-output/discovery-ready.json

python -m m2.product_service --mode query --database /absolute/isolated/core.sqlite \
  --binding /absolute/host/pinned-binding.json \
  --authority /absolute/host/runtime-authority.json \
  --private-config /absolute/existing-ragflow-config --port 0 \
  --ready-file /absolute/new-output/query-ready.json

python -m m2.product_service --mode history --database /absolute/isolated/core.sqlite \
  --binding /absolute/host/pinned-binding.json \
  --authority /absolute/host/history-authority.json --port 0 \
  --ready-file /absolute/new-output/history-ready.json
```

These are three separate foreground processes; stop the specific PID with SIGTERM
or Ctrl-C. Worker joins are recorded in each `.stopped.json`. No Agent stop is
implied. Credentials are Host-provisioned private files, never command arguments.
Missing authority fails closed; readiness is not authorization acceptance.
The history process rejects outbound sockets and accepts no RAGFlow configuration.
Ports 61353, 61358 and 61360 are prohibited. Original H1a CLIs are unchanged.
Install optional `documents` dependencies and use the repository root on PYTHONPATH.

## Joint acceptance still required

Contract/export tests and local HTTP discovery tests do not close Builder delivery.
Harness must still show server-authorized selection, managed configuration and
installation association, actual Factory/RAGFlow query with original anchors,
version/source denial and independently authorized stopped-instance history.
New synthetic products are created only in isolated databases by existing trusted
test preparation, never by this service. No new H1a claim or H1b development here.
