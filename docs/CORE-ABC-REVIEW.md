# A-C independent review tranche

This branch is based directly on M0 main `bd725263`, through the original ordered
commits A `116e69f`, B `684217c`, C `02e59a5`. No D/UI implementation is included.
It does not depend on PR #7 or the old Draft chain. Nothing has been merged.

## Review order and scope

1. A: `knowledge_core/evidence`, public anchor contracts and focused tests.
2. B: `knowledge_core/documents.py`, document contracts, `m2/pipeline.py`, bounded
   native `m2/ragflow.py`. Isolated document lifecycle, not production IAM.
3. C: query/session/history protocol and services, verified Host leases, fixed
   binding, current permission checks, zero-execution historical reads.

Independent regression on this A-C-only tree: **274 passed, 12 known JUnit
record_property warnings** (`evidence/premerge-gates/abc-regression.xml`).
There are no UI imports, rule-extraction experiments, Wiki workers or automatic
service starts. The small M0 reference Rule IR remains the unchanged M0 baseline.

## Additional integration gates

The A-C Core/contracts/pipeline/RAGFlow/Runtime files are byte-identical to those
in the separately tested Factory `d67d366` and `1bf631a` candidates. They have no
dependency on D. Integration evidence executes those exact full-candidate SHAs,
not this new documentation/evidence commit. This distinction is intentional.

- Native `d67d366`: actual HTML upload, RAGFlow parse/index, Core validation,
  separate test approval/binding and query; 3/3 supplied synthetic retrieval tests.
  Original report and all runtime implementation hashes were checked against Git.
- Native `1bf631a`: new run `run-28b1c6ca1d514e3485be2b64377dd7a9`, same unchanged
  backend, new synthetic source and index; 3/3. This also tested the separately
  retained D usability change. It is not general retrieval-quality acceptance.
- Cross-repository: Factory `d67d366`, Builder
  `08a0c858c083cce97f29dc928011a76a65814c6e`, Harness
  `622e374bb6f2a8455c8f6d1fc976cbd9bd87eb4d`; **60/60** checks.
  Real managed installation, Java Provider and Factory HTTP, controlled model.
- Agent `agent-eac6d78a03054c1f`, instance
  `09a8b578-67ff-42e7-8c9d-ca71c0b6ce37`, original fixed Manifest
  `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
- Same-instance history verified original answer/anchors and independent Host
  permission, with 0 outbound attempts, 0 model calls, 0 new query receipts.
  Source/Host revocation, mismatch and outage fail closed. Original DB unchanged;
  tests used a backup and an independent Maven cache. Processes were stopped.

Inspect `cross-repository/same-instance-binding.json` for Lock/receipt identities
and `report.json` for all checks. Raw success/denial responses and DB fingerprints
are retained. Evidence contains no Host secrets, leases or raw databases.
Initial environment and controlled-fixture failures remain in PR #7's
`evidence/premerge-gates/failures`, not overwritten as successes.

## Enablement and remaining review

Review approval is required before merge. A-C can be approved as this explicit
tranche or in A/B/C order; do not merge PR #7 wholesale alongside it. Once A-C is
merged, prepare and retest D as a main-based UI-only change. Existing PRs #1-#6
and 229 original historical records remain preserved on their original branches
and the PR #7 review envelope. Do not remerge those experiment branches.

Production IAM/Host trust, source governance, distribution and deployment still
need a separate review. P08/P43, Wiki, general PDF/Word, H1b and other production
lines are not accepted by this tranche. No production port, grant, source
activation or deployment is changed. 61353 and zhishi are not replaced.
