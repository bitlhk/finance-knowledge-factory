# Trusted evaluation services acceptance

## Scope

This report covers PR #13 at `f64ca5e2e50280fb826763611d724df54b18bc72`.
The acceptance used an isolated database, synthetic candidate, dedicated Unix
sockets, and dedicated operating-system identities. It did not modify or
restart `knowledge-zhishi-preview.service`, its database, any published product,
or the PR #9 integration environment.

## Runtime boundary

| Role | Linux identity | May read | Must not read |
| --- | --- | --- | --- |
| Core | `kf-eval-core` (UID 996) | isolated Core database, retrieval credential | model credential, Worker handoff |
| Worker | `kf-eval-worker` (UID 995) | own role credential, fixed task references | Core database, retrieval credential, model credential |
| Gateway | `kf-eval-gateway` (UID 994) | model credential, own role credential | Core database, retrieval credential, Worker handoff |
| Host | `kf-eval-host` (UID 993) | Host credential, read-only Worker handoff | model credential, Core database |

Core and Gateway ran as separate managed services. The Worker ran as a managed
one-shot service. AF_UNIX requests were authenticated with both `SO_PEERCRED`
and a role credential. The Worker-to-Host result handoff used a separate
setgid group; Core and Gateway were denied access. File access checks were
performed as each real service user, not inferred from metadata.

The threaded Core service opened and closed one `DocumentCore` connection per
request. A real SQLite/Unix-socket concurrency test confirmed one atomic lease
consumption under two concurrent calls and `PRAGMA integrity_check=ok`. SQLite
thread checks remain enabled. The Gateway used one persistent asyncio event
loop for all six invocations and had zero restarts during the run.

## Real six-case execution

The managed Worker queried the isolated candidate and invoked the registered
Volcengine DeepSeek deployment through the Gateway for six fixed cases. Core
then correlated the immutable candidate and model receipts and independently
created:

- runtime evidence: `8beff084b306d4aed035685086860f27d7b60ffa18571ca5cdb9065012ae0f80`
- answer evaluation: `79b932376589a3fa38139a9135924d2d3459e070e00c4707c3afda100b126d69`
- quality admission: `f67c3053b023d40812acb111b2292a3b7c6cc2b2203e569bb0a3af2043d47b8e`

The runtime verification is `CORE_CORRELATED_FACTORY_WORKER`. Core calculated
fact, citation, and forbidden-claim accuracy as 10000 bps and made the Quality
Admission decision `PASS`. The Worker did not receive a quality-decision or
publication operation, and there is no publication operation in either IPC
facade.

## Negative acceptance

The isolated services produced these fail-closed results:

- valid Worker credential from the wrong UID: `EVALUATION_SERVICE_UNAUTHORIZED`
- invalid credential from the correct Worker UID: `EVALUATION_SERVICE_UNAUTHORIZED`
- Worker calling Host finalization: `EVALUATION_SERVICE_OPERATION_FORBIDDEN`
- repeated one-shot Worker execution: `EVALUATION_LEASE_REPLAYED`
- forged model receipt in Host finalization: `NOT_FOUND`; no new Admission
- stopped/missing Gateway after a real candidate receipt and authorization:
  invocation failed before a model receipt; Admission count did not change
- source revocation before a subsequent query: `SOURCE_SUPERSEDED_OR_REVOKED`
- RESTRICTED source bound to a non-external authorization: external Gateway
  authorization rejected with `EVALUATION_EGRESS_FORBIDDEN`; no model request
- a real five-minute lease queried after its deadline:
  `EVALUATION_LEASE_EXPIRED`
- forced Core and Gateway `SIGKILL`: systemd restored each isolated service and
  recreated its mode `0660` socket; no quality result was synthesized

Existing unit and integration coverage also retains failed model attempt,
revoked lease, receipt mismatch, replay, and unknown deployment cases.

## Regression and compatibility

- local Python 3.12 suite: `396 passed`
- targeted service-boundary and handoff suites: `13 passed`
- GitHub CI: `m0 (3.10)` and `m0 (3.12)` passed at the PR head
- PR head remained mergeable during acceptance

External Manifest, publication, query, authorization, and history contracts are
unchanged. The service templates and task preparation tool are internal. The
formal Knowledge Factory service and old v0.1 products were not used as mutable
test fixtures.

## Deployment boundary

This acceptance proves process and filesystem separation on the development
host. Production enablement still requires provisioning the documented users,
groups, role credentials, directories, qualified model registration, and
systemd units through the deployment process. It does not make the Worker a
public service and does not expose a workbench action. PR #14 remains out of
scope.
