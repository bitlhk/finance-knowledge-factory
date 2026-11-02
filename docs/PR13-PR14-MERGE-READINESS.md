# PR #13 and PR #14 merge readiness

## A. Code review and merge preparation

### PR #13

Fixed review HEAD: `67352c7a8cbb7b36c66b278683297950df0b4828`.
Python 3.10/3.12 CI passes and GitHub reports the PR mergeable. There is no
independent review, so it is not approved for merge.

The independent reviewer must resolve two additional findings from the PR #14
isolated acceptance before approving:

1. `prepare_evaluation_service_task.py` does not emit all fields consumed by
   `_core_boundary()`: `purpose`, `redactionProfile`,
   `authorizationExpiresAt`, `pythonVersion`, and `openJiuwenVersion`. Directly
   placing its output into `fixedTask` caused `KeyError` restart loops. The
   accepted run required a manual trusted-host merge. This is an unresolved
   provisioning/config-contract defect, not a model-quality failure.
2. A real model invocation failed with receipt
   `872bb92d50d7d87e5e0fbbb6776e40e3c93e27a8b13492b367bf8eff448ac7a1`.
   The receipt records only `errorClass=ValueError`; it cannot distinguish the
   Gateway's bounded empty-response/oversize errors from an SDK/provider
   `ValueError`. The retry succeeded with a fresh Assignment/Lease, but the
   original cause remains unclassified. A safe bounded failure code or an
   explicit reviewer-approved residual-risk decision is required.

These findings do not invalidate the fail-closed behavior: no PASS was created,
the failed lease was not reused, and the successful retry used new authority.
They do prevent treating retry success as closure.

Reviewer material and the full permissions checklist are in
`docs/PR13-INDEPENDENT-REVIEWER-HANDOFF.md`. The author must not self-approve or
bypass the review requirement.

### PR #14

Current stacked HEAD: `b7691e6d87eee9f0b663cc21a6bdd28480777417`, based on
PR #13. Python 3.10/3.12 CI passes, local regression is `449 passed`, and GitHub
reports a clean mergeable stacked diff.

The intended code scope is limited to:

- existing workbench orchestration and UI;
- trusted workbench authority resolution and separation of duties;
- controlled AMSYLJ01 source conversion/provenance;
- quality publication binding and deterministic quality checks;
- fixed business tests, immutable evidence and supporting tools.

No external Manifest, query or history schema file changes are present. Existing
contract/regression tests pass.

Formal enablement remains fail closed:

- the only runnable M2 CLI requires `--isolated-test-preview`, binds loopback,
  rejects reserved formal ports, and uses explicitly synthetic isolated
  authority;
- formal `WorkbenchAuthorities` requires a server-owned resolver and rejects
  missing authentication, missing roles and synthetic principals;
- no evaluation launcher returns `EVALUATION_SERVICE_NOT_READY`;
- forged evaluation results cannot create approval;
- PASS does not activate a source, approve or publish automatically;
- formal identity and deployed trusted-service assembly are not implemented by
  this PR and must not be represented as enabled.

After PR #13 is independently approved and merged, PR #14 must be rebased onto
the resulting `main`. Review the rebased diff, rerun CI and affected security/
compatibility suites, provision a real authenticated resolver only in an
isolated acceptance environment, and obtain an independent security review.
Only then may PR #14 be moved from Draft to Ready for Review.

Recommended merge order:

1. independent PR #13 review, requested fixes or explicit residual-risk
   disposition, then controlled merge and record the Merge SHA;
2. rebase PR #14 on that exact `main`, verify the workbench-only diff and gates;
3. independent PR #14 engineering/security review;
4. code merge approval, separately from any product release decision.

## B. Product admission

AMSYLJ01 remains **REJECT** with five real business errors. The immutable list
is in `docs/AMSYLJ01-QUALITY-REJECT-FREEZE.md`. Engineering review or merge of
PR #13/#14 does not approve, publish, or create a Manifest for this candidate.
