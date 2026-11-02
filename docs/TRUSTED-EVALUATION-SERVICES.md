# Trusted evaluation services (PR #13)

## Purpose

PR #12 proved the fixed evaluation flow but ran Worker, Core, and Gateway in one
Python process. This change introduces the narrow local IPC boundary required
before real model evaluation can be exposed from the Knowledge Factory
workbench. It does not change publication, Manifest, query, or history contracts.

## Service split

| Process | May hold | Exposed operations | Explicitly excluded |
| --- | --- | --- | --- |
| Core evaluation service | Core database, candidate retrieval configuration, server-owned actors | candidate query, bounded egress authorization, gateway prepare/record, Host finalization | publication, policy management, source activation, arbitrary object access |
| Evaluation Worker | assignment/lease references, Worker credential | fixed case loop through Core and Gateway IPC | database path, model secret, PASS calculation, Admission, publication |
| Model Gateway | model credential, qualified deployment identity, Gateway credential | invoke a Core-prepared request and record its actual result | candidate query, quality decision, publication |
| Trusted Host | Host credential and task references | finalization of one frozen evaluation | model secret, direct answer fabrication, automatic publication |

Core owns all actors used by its facade. Caller-provided principal, authority,
privileges, model endpoint, deployment, Candidate, test set, profile, expiry, and
quality configuration are not accepted in IPC requests.

The threaded Core socket creates and closes one `DocumentCore` connection per
request. It does not share a SQLite connection across request threads and does
not disable SQLite's thread ownership check. Core transactions and immutable
object checks remain the concurrency boundary. The Gateway owns one persistent
asyncio event loop for all model invocations in that process.

## Authentication

The transport is an AF_UNIX socket. Every request is authenticated by both:

1. Linux `SO_PEERCRED` UID from the connected process; and
2. a role-specific credential whose SHA-256 digest is held by the server.

The server defaults to refusing startup unless Host, Worker, and Gateway map to
three distinct positive UIDs. Socket permissions are applied at creation. The
credential value is never included in a response or error.

Distinct credentials without distinct operating-system identities are useful
only for transport unit tests and are not an accepted deployment mode.

The Worker writes its immutable run handoff with mode `0640` into a pre-created
setgid directory owned by a separate `kf-eval-handoff` group. Only the Worker
and trusted Host belong to that group. Core and Gateway use `kf-eval-ipc` for
socket access but cannot read the handoff file.

## Fixed operation matrix

| Operation | Caller |
| --- | --- |
| `candidate.query` | Worker |
| `model.authorize` | Worker request, Core executes with its fixed Host actor and frozen task binding |
| `model.invoke` | Worker to Gateway |
| `model.prepare`, `model.record` | Gateway to Core |
| `evaluation.finalize` | Host |

There is deliberately no publication operation. `evaluation.finalize` asks Core
to correlate immutable receipts, calculate answer quality, and create a Quality
Admission. A later workbench integration must require a separate authenticated
human publication action and call the existing quality publication path outside
these services.

## Remaining deployment acceptance

This PR is still Draft until an isolated environment proves all of the following:

1. Separate system users and filesystem views for Core, Worker, and Gateway.
2. Core is the only process with the database and candidate retrieval config.
3. Gateway is the only process with the model credential.
4. Worker cannot open either path and cannot call Host/Gateway-only operations.
5. A controlled Host starts one real DeepSeek evaluation and receives Core's
   independently calculated result.
6. Credential mismatch, peer UID mismatch, lease expiry, source revocation,
   restricted-source egress, replay, process crash, and forged receipt all fail
   closed.
7. No current `zhishi.linggan.top` service or historical product is modified.

Only after this acceptance may PR #14 expose a real-model evaluation action in
the workbench.
