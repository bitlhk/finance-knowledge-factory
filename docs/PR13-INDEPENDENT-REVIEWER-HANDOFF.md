# PR #13 independent reviewer handoff

Review target: `feat/trusted-evaluation-services@67352c7a8cbb7b36c66b278683297950df0b4828`.
The PR is Ready for Review, mergeable, and its Python 3.10 and 3.12 checks pass.
It has no submitted independent review. The author must not self-approve it.

## Review boundary

Confirm that the implementation proves only the documented development-host
isolation boundary. It does not claim that the Worker is a public service or
that production identities and credentials have already been provisioned.

Review these points directly:

1. Core opens a request-scoped `DocumentCore`/SQLite connection and preserves
   atomic lease consumption, revocation and receipt writes under concurrency.
2. AF_UNIX requests require both `SO_PEERCRED` and a role credential; each role
   can invoke only its declared operations.
3. Worker cannot read the Core database, retrieval credential or model
   credential; Gateway and Core cannot read each other's private state.
4. Gateway alone resolves the registered endpoint, model and external-egress
   properties. Worker input cannot downgrade an external model to internal.
5. Core recomputes Runtime Evidence, Answer Evaluation and Quality Admission;
   Worker cannot submit PASS or publish a product.
6. Replay, expiry, source revocation, forged receipt, wrong UID/credential,
   Gateway failure and service crash all fail closed without creating PASS.
7. The service templates do not expose sockets publicly and do not depend on
   PR #9 or another development worktree.
8. External Manifest, query, history and publication contracts remain
   unchanged.

## Evidence to inspect

- Architecture and permission matrix: `docs/TRUSTED-EVALUATION-SERVICES.md`.
- Real process and filesystem acceptance:
  `docs/TRUSTED-EVALUATION-SERVICES-ACCEPTANCE.md`.
- Accepted runtime evidence:
  `8beff084b306d4aed035685086860f27d7b60ffa18571ca5cdb9065012ae0f80`.
- Accepted answer evaluation:
  `79b932376589a3fa38139a9135924d2d3459e070e00c4707c3afda100b126d69`.
- Accepted Quality Admission:
  `f67c3053b023d40812acb111b2292a3b7c6cc2b2203e569bb0a3af2043d47b8e`.
- Regression at the reviewed head: Python 3.10 and 3.12 GitHub checks are
  successful; the acceptance report records `396 passed` and the focused
  service-boundary suite records `13 passed`.

## Required reviewer outcome

Record an independent approval or concrete requested changes against the exact
HEAD above. A newer HEAD requires the affected checks and review to be repeated.
Do not merge or deploy based solely on this handoff document.
