# Main convergence preparation (not a merge or production release)

Frozen source: `160aaf51b2a54664434d5c17bc3aa95a1b75b693`.
Stable base: `bd725263e4c7d28b14fba9e665d9d180e68e84c8` (`main`).
One short-lived branch based directly on main, with ordered review units. This is
not another child of PR #6. PR #1-#6, source branches and saved evidence remain
unchanged. Review individual commits; do not merge the entire historical stack.

## Ordered units

1. **A: sources and contracts.** Native HTML location/bridge primitives and the
   historical JSON-evidence digest move out of probes. M0 hashing, rules, schema
   and grants remain unchanged. These functions do not extract business rules.
2. **B: document service.** Document Core, immutable document contracts, production
   adapter and bounded native RAGFlow transport. No UI, LLM or Flowable dependency.
3. **C: Runtime.** Frozen query/session/history contracts, Host lease verifiers,
   fixed binding and standalone consumers. No authority issuance or publication.
4. **D: V1.5 UI.** Existing four entries and three-column assets remain byte-identical.
   Isolated document workshop only; unaccepted rule/Wiki execution stays outside
   the candidate. Synthetic test grants/activation are not production IAM.

B needs A, C needs A+B, D needs A+B; C is not a dependency of UI production.
Each prefix is tested independently. Full source-candidate regression and explicit
old/new equivalence checks supplement prefix tests; different scopes are not added
together as a new business-quality score.

## Boundaries

- Engineering merge eligibility is not banking approval or production readiness.
- P08/P43 semantic correctness, Wiki, PDF/Word generality and production IAM remain
  unaccepted. The approved H1a technical sample does not promote them.
- No service starts on import. Isolated preview requires an explicit launch, not
  public hosting. No existing 61353/61359 process is restarted for this preparation.
- Preserved evidence keeps original code/commit identities and failed results.
  New checks have their own identities; no old Manifest or score is regenerated.
- H1a instance, Manifest, Lock and receipt references stay in the frozen record.
- Optional document dependency is separate from the M0 dependency set.

Detailed dependency inventory, selected paths, execution results and review gates
are recorded with the final preparation evidence, not inferred from a test count.
