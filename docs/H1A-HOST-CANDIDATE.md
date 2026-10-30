# H1a Host candidate, 2026-10-30: installation NOT accepted

This report supersedes the *current-state* portion of H1A-INTEGRATION-PROGRESS.md.
Earlier reports, scores, source identities and failed attempts remain unchanged.
This is an isolated development candidate, not a production deployment.

Paired candidate commits: Harness `3dacab0` on `feat/knowledge-h1a-evidence`,
Builder `4067f014` on `feat/knowledge-h1a-host`. The actual build reports below
precede these commits and retain their original dirty-tree identities.

## Actual progress

- A separate `knowledge-read-only` Profile and knowledge Host declaration now use
  the existing OpenJiuwen Java runtime and managed scenario preparation SPI.
  No knowledge endpoint was added to the bank connection allowlist.
- `integrations/knowledge-java` implements the actual scenario extension. Build
  preparation verifies locked metadata only. Runtime uses an independent private
  Host policy, issues bounded per-session leases, and constructs the existing
  managed Knowledge Provider. It does not use BankAccess or mutate Core authority.
- Core's `HostLeases` resolves only private, owner-controlled policy/lease files.
  Lease files contain a hash-addressed credential reference, not the bearer value.
  They bind owner, instance, session, product, Manifest, context and policy digest.
  This is an isolated operator-owned authority, **not production IAM**.
- A consumption-only `/session` check re-evaluates the current Core binding and
  source/service permissions without retrieving content. The scenario calls it
  before model execution and before returning results. A grant or source revoked
  after a tool result must not be accepted merely because the lease still exists.
- Context can carry the Host's currently qualified collectors. Existing Context
  constructors remain available. New knowledge code cannot self-declare VERIFIED.
- SDK installations are serialized across knowledge sessions because the SDK tool
  registry is process-global. Cancellation remains a request, not a cleanup claim.
- Builder's same-process registry-lock defect is repaired using an in-process
  reservation before opening the OS lock file. The existing cross-process lock
  protocol is retained, including compatibility with the older lock implementation.

## Real build result, not an installation receipt

The actual Builder `build_service(verify=True, managed=True)` ran three attempts.
All used the fixed actual M2 product and Manifest below, and isolated Maven cache.

| Attempt | Result |
| --- | --- |
| 01 | Catalog governance fixture digest was stale after adding the new Profile; rejected by contract validation. Retained. |
| 02 | Contracts, Harness tests/install and candidate packaging passed. Component preparation rejected `OBSERVATION_REQUIREMENTS_UNMET`. |
| 03 | Same stages passed with the current authority/session checks and scenario tests. Still rejected `OBSERVATION_REQUIREMENTS_UNMET`. |

The `capability.result` requirement remains REQUIRED. The new artifact has no
verified collector qualification for its actual runtime/dependency identity.
An old bank build's collector result is not transferable just because both use
Java. Nor can a successful compile or a synthetic `passed:true` file qualify it.

The generated `service-lock.json` is a build file lock. **There is still no
successful Agent Installation Lock, Agent UI tool receipt, or same-Agent stop and
history receipt.** H1a-1 and H1a-3 are not passed. H1a-2 remains protocol-tested,
not accepted through an installed Agent.

The attempt reports record dirty source trees at Harness `a2db416` and Builder
`9b4b5be4`, along with locked build files and hashed stage logs. Do not relabel
these executions as later committed SHA runs.

## Validation scope

- Factory regression: **356 passed**, including 30 lease/runtime tests. No new
  real model call or live RAGFlow query was required for this test run.
- New Java authority tests: **6 passed**. Tests cover independent scoped leases,
  expiry/owner/Manifest rejection, policy revocation, changed lease identity,
  file privacy, HTTP-200 business denial and release of only the owned lease.
- Actual candidate Maven contract/test/package stages passed; admission failed.
- Builder full local suite: **2973 passed, 75 skipped, 3 failed**. This invocation
  did not set optional cross-repository/compiled-candidate environment variables;
  it is not a same-coverage numerical comparison with the earlier 2983/62/5 run.
- Builder's cross-repository customer-manager/audit/access subset: **41 passed,
  1 failed**. The failure is the existing customer-manager directory Profile
  expectation; this is not full two-scenario acceptance.

## Remaining regression risks

| Existing failure | Diagnosis and disposition |
| --- | --- |
| Same-process single writer | OS record locks are process-scoped; a duplicate open/close can release the original lock. Fixed without changing the cross-process protocol; regression checks duplicate thread, independent process and reacquisition. |
| Public API exports | Actual package exports six Runtime Builder names beyond the asserted portable candidate API. Contract mismatch retained; removing exports could break consumers, while widening the expected set without review would hide it. |
| Customer-manager Profile | Actual directory includes `local-read-only` as well as `employee-assisted`; the test requires employee-only. Retained pending audience/Host compatibility review, not waived as a cosmetic test. |
| Two package process cleanup tests | `EVAL_PACKAGE_CLEANUP_UNKNOWN` persists. The marker-based Linux process scanner fails closed on an unreadable/unknown process. Do not skip it, signal unrelated processes, or infer all resources were released. Actual knowledge Host lifecycle cleanup still needs its own evidence. |

## Preserved live boundary

Read-only `/api/state` inspection confirmed port 61353 still reports
`c2939742f211a1ed363dc792d3602d0098765a04`, `dirty=false`,
`M2_ISOLATED_DOCUMENT`. No service restart, source activation, grant creation or
production configuration change was performed. The new lease service was not
started and no operator authority file was created.

- Product: `run-39d069d400924257a857cfa7ec64917b`
- Manifest: `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`
- Original Core database: `/home/ubuntu/outputs/knowledge-m2-web/app/core.sqlite`
- Build attempts and test XML: `/home/ubuntu/outputs/knowledge-h1a-host-builds/`

Selected original build and regression records are also retained in
`evidence/h1a-host-candidate/`; they explicitly preserve failed assertions and
the rejected installation. They are not successful lifecycle receipts.

## Remaining implementation, in order

1. Extend the reviewed collector qualification workflow to the knowledge Host's
   actual artifact identity, retaining REQUIRED observation. The old qualifier
   assumes bank login/source/model fixtures and is not a knowledge Host test.
2. Wire server-owned provider bindings and authority configuration through Jobs
   and its existing managed startup path. The build runner currently calls the
   real Builder service, but is not the My Agent creation UI. Do not expose an
   arbitrary endpoint, identity, Manifest or date as model/browser authority.
3. Install one Agent, query this same Core snapshot from Enter App, then run all
   denials, stop and history checks on that exact instance. Bind archive records
   to the real Installation Lock and confirm callback collection and disposal.

No H1b, new Runtime, UI redesign, production merge, rollout or semantic-rule
quality acceptance is included. PR 6 and PR 96 must remain Draft.
