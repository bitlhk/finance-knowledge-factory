# Knowledge Factory mainline convergence

## Purpose

This candidate establishes one supported baseline for document knowledge
production and consumption before the financial-document quality work starts.

## Included

- evidence primitives and document Core;
- query, history, Host lease and Runtime contracts;
- Host-authorized product discovery with pinned manifests and connection refs;
- bounded RAGFlow query-session reuse;
- the isolated document production workspace and responsive UI;
- stable paginated chunk-visibility checks.

The candidate preserves authorization, manifest pinning, history-read isolation,
and source-revocation behavior. It does not make rule experiments executable.

## Excluded

- the M1 rule-lowering experiments;
- the Wiki worker probe;
- any new H1b feature or production deployment change;
- credentials, leases, cookies, databases and private runtime configuration.

The corresponding historical branches and evidence remain available for audit,
but they are not continuing development baselines.

## Verification

- exported contract check: no diff;
- repository regression: 345 tests passed on Python 3.12;
- synthetic M0 lifecycle walkthrough: completed locally without retaining the
  regenerated timestamp-bearing evidence file;
- remote Python 3.10 and 3.12 CI: required before merge.

After this candidate reaches `main`, financial-document retrieval and grounded
answer quality work must start from the updated `main` in a separate branch.
