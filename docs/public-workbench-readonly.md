# Public workbench read-only boundary

The public development workbench is not an authenticated production workspace.
`--isolated-test-preview` supplies synthetic identities; same-origin checks are
not authentication. The HTTP adapter now defaults to read-only and rejects every
POST before body parsing or business calls, including queries that create receipts.
Public state excludes workspace sources, runs and release history. Historical
test data remains on disk, but stale browser task selection is discarded.

Only explicitly private test deployments may set
`KF_WORKBENCH_ACCESS=isolated-write`. Never set this on a publicly proxied service.
Request headers, cookies and frontend controls cannot change this mode. This is a
temporary closed boundary, not an implementation of SSO authentication.

Public readers can inspect the operator-configured publication catalog, verified
fixed Manifests and original pages. Publication metadata is projected from checked
read-only records; it is not an access grant. Authenticated DSH/MCP consumption
remains a separate service with its existing authorization checks.

## Page responsibilities

- Sources: grouped source files and original pages; upload unavailable until login.
- Production: no anonymous workspace history; explicit empty/closed state.
- Artifacts: development releases, quality and provenance; technical details on demand.
- Consumption: authenticated plugin entry; no fabricated Agent inventory or logs.

Browser verification queries are unavailable pending server authentication and
resource limits. React migration, shared workspaces and production banking
authorization are not included.

## Verification and release

Run `python -m pytest -q`. The browser CI runs a real HTTP adapter with synthetic
publication fixtures at 1440px and 390px, checks stale selection, original text,
overflow and same-origin mutation denial, and archives screenshots. It does not
claim that fixture evidence is live bank-product acceptance.

Deploy a fixed commit into a separate release directory. Back up the service
drop-in and use SQLite online backup before switching only the public workbench
service; keep database, private configuration and publication paths unchanged.
Repeat checks against the public domain after restart. Do not auto-merge this PR.

Rollback must preserve the read-only security boundary: do not restore the old
anonymous write service on a public route. If rollback to old code is unavoidable,
first close the public route (or enforce equivalent upstream method and private
state restrictions), then restore the previous release. Do not restore databases
over newer query receipts merely to roll back frontend code.
