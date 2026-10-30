# H1a integration progress: not accepted

Historical checkpoint. For subsequent Host implementation and remaining
installation blockers see [H1A-HOST-CANDIDATE.md](H1A-HOST-CANDIDATE.md).

Checked 2026-10-30. This is a partial implementation report, not an H1a completion
or deployment claim. PR 6 and Harness PR 96 remain Draft. No UI redesign, M0
rewrite, H1b implementation, branch rebase, or production deployment was performed.

## Fixed live boundary

Port 61353 still reports commit `c2939742f211a1ed363dc792d3602d0098765a04`,
`dirty: false`. No process restart or replacement was performed. The running
process captured its baseline before these additive source edits.

The actual existing isolated M2 product is
`run-39d069d400924257a857cfa7ec64917b`, Manifest
`8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
Its material is synthetic, but it was produced and published by the actual M2
pipeline; it is not a standalone Knowledge Provider HTTP fixture.

## Implemented

- `m2/harness_runtime.py`: consumption-only protocol adapter. An injected trusted
  resolver authenticates a bounded lease. Browser/model JSON cannot create an
  Actor, business context or authorization. Core admission runs before upstream
  construction and after retrieval; session expiry/revocation is rechecked.
  There are no grant, source-activation, approval or publication endpoints.
- Receipt mapping retains request/trace, product, Manifest, source/revision,
  index, current policy, binding and immutable Core receipt identity.
- Harness component-owned installed configuration reader verifies configuration
  bytes against the Builder service file Lock, then constructs the managed
  Provider without acquiring runtime authority. This is NOT an Agent installation
  Lock or a trusted Host authority implementation.
- Builder candidate adds server-owned per-Provider connection/configuration
  descriptors, exact selected artifact build closure and an opt-in use of the
  existing scenario preparation SPI. No existing Host is silently opted in.
- Pure knowledge solution and independent test set replace the bank balance
  selection template. The actual knowledge build remains rejected at admission.

## Results and evidence

| Check | Result | Boundary |
| --- | --- | --- |
| Factory Python regression | 343 passed | local regression, no Agent |
| Adapter negative/HTTP tests | 17 passed, included above | expiry, spoofing, current permissions, future source, upstream errors |
| Actual M2 consumption r2 | 3 queries + 4 negative checks passed | direct protocol, not Java Provider or UI |
| Knowledge Java tests | 27 passed, including 6 installed-config tests | no installed Agent |
| Builder full regression | 2983 passed, 62 skipped, 5 failed | NOT a green release gate |
| Preparation SPI native checks | 7 passed | controlled fixture against compiled Host, not knowledge installation |
| Bank regression build | BUILT; 32 runtime checks; 6 install-negative checks passed | bank path only |
| Knowledge Builder attempt | ASSEMBLY_PROVIDER_CONNECTION_MISMATCH | no candidate, no installation Lock, no Agent |

The five Builder failures also reproduce on the unmodified Builder `9d33295`:
public API export assertion, customer-manager directory profile expectation,
two process-tree cleanup checks (`EVAL_PACKAGE_CLEANUP_UNKNOWN`) and the
same-process single-writer lock check. Their failures are retained, not waived.
No statement of complete customer-manager/audit regression or OS cleanup follows.

Local immutable evidence locations:

- `/home/ubuntu/outputs/knowledge-h1a-core-check-r1/result.json`
- `/home/ubuntu/outputs/knowledge-h1a-core-check-r2/result.json`
- `/home/ubuntu/outputs/knowledge-h1a-core-pytest-final.xml`
- `/home/ubuntu/outputs/knowledge-h1a-builder-pytest-final.xml`
- `/home/ubuntu/outputs/knowledge-h1a-baseline-failures.xml`
- `/home/ubuntu/outputs/knowledge-h1a-bank-regression/r1/candidate/`
- `/home/ubuntu/outputs/knowledge-h1a-bank-install-negatives-r1/`
- `/home/ubuntu/outputs/knowledge-h1a-pure-admission-r1/h1a-admission.json`

The direct check uses the native RAGFlow retrieval adapter. Its historical
`nativeOperations` array records ingestion stages only, not retrieval requests;
an empty array does not mean zero calls or complete request collection. Do not
reinterpret it as Agent tool-attempt evidence. Generative model calls: zero;
cost: unknown. Source revisions, policies, active bindings and activations on the
original product remain unchanged. Queries append their own receipts. Negative
policy mutation is restricted to an exact private SQLite backup.

## Unfinished H1a gates

1. **H1a-1**: reviewed knowledge Host support/connection admission, a real scenario
   extension using the preparation SPI, qualified observation and actual managed
   Agent installation. Configuration validation alone does not satisfy this gate.
2. **H1a-2**: trusted runtime supplier issuing/revoking the knowledge session and
   Grant independently of BankAccess; connect the real Java Provider to the Core
   adapter. The current test lease is not that production/runtime integration.
3. **H1a-3**: existing My Agent/Enter App surface, model-controlled installed tool
   invocation, UI negative cases, history and stop/release receipts from that
   same knowledge instance. None has been executed.
4. Repeat bank/customer-manager/audit compatibility on the paired committed
   candidate, resolve or explicitly gate the baseline failures, and preserve
   all earlier failed attempts. Bank success cannot replace knowledge cleanup.

Do not enable the new preparation feature in a Host declaration until its actual
scenario implementation and collector admission are ready. Do not add knowledge
to the bank connection allowlist to make the admission error disappear.

See `H1A-DEPENDENCY-AUDIT.md` for source dependencies and a proposed merge order.
This report freezes partial work only. It does not satisfy the user's end-to-end
acceptance worksheet.
