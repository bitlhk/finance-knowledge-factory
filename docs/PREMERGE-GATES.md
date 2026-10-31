# Pre-merge gates and split review

Status: **ready for engineering review, not merged or production enabled**.
PR #7 is still the complete review envelope, not an instruction to merge A-D.
The old PRs #1-#6, 229 original evidence files, M0 contracts and V1.5 reference
HTML are preserved. No service on 61353 or zhishi was replaced for this review.

## Review units

| Unit | Implementation | Gate | Proposed disposition |
| --- | --- | --- | --- |
| A | `116e69f` | Original 130 prefix tests; source provenance unchanged | Review first |
| B | `684217c` | Native RAGFlow/browser/Core smoke on `d67d366`; new native smoke on `1bf631a` | Eligible for document-only isolated scope |
| C | `02e59a5` | New fixed-version cross-repository acceptance: 60/60 | Eligible for query/session/history contracts |
| D | `b906b78` + `1bf631a` | Upload and guided sample browser checks; native smoke 3/3 | Await user product acceptance, not production approval |

An independent `review/core-abc-160aaf5` branch starts at the actual A+B+C
prefix of main, not PR #7. It contains no `web_production`, `web_preview`,
`m2/web.py` or `m2/web.js`. Its isolated Python regression is **274 passed**.
Review A, then B, then C in this branch. It can be merged as one explicitly
approved A-C tranche, or as those three commits after separate approvals.
Neither operation has been performed. D remains outside that PR.

After A-C approval and merge, prepare a clean main-based D-only change using
the reviewed D commits; do not merge the old stacked PRs or assume retargeting
PR #7 is sufficient. Record the new SHA and rerun UI/Core regression. Do not
rewrite historical receipts to match the new Git history.

## Native document gate

The domain setup test already executed PR #7 `d67d366` against real RAGFlow:
`run-8690442f8eb64a21bfd8fefe515cece5`, Manifest
`4991c2ad8692b81d1e7470b144cb650e63b5324ed0fe920abf0a9909d57de254`.
Its saved implementation hashes have now been checked against that exact commit.
This is existing evidence newly included here, not a new execution this turn.

A **new** native browser smoke used clean `1bf631a`, isolated temporary Core
state, a new synthetic HTML source and the existing authorized local RAGFlow:

- Run: `run-28b1c6ca1d514e3485be2b64377dd7a9`.
- Manifest: `730d308769b3234c41b0a17b4f9ff1d47802c7cafb7b37a2ddc71820430e9552`.
- Real upload, parse/index, three supplied retrieval tests (3/3), Core candidate,
  separate test approval and binding, then an anchored query.
- No generative LLM calls; the local embedding/index service was used. No
  generated FAQ or semantic-quality claim.
- Refresh issued no POST/reexecution. 320px/390px layout and JavaScript checks
  passed. Guided examples are deliberately supplied tests, not blind questions.
- Test indexes remain in the isolated RAGFlow account for evidence retention;
  this does not claim full artifact cleanup. Temporary HTTP servers were stopped.

Core, contracts, document pipeline, RAGFlow and Runtime files are byte-identical
between prefix `02e59a5`, `d67d366` and `1bf631a`. The new UI commit changes only
two JavaScript files and browser test tooling. Original native failures and scores
are not overwritten. See `evidence/premerge-gates/INDEX.json` and raw receipts.

## Cross-repository gate

New execution, not inferred from the old H1a report:

- Factory: `d67d366f8aeabee15365c661055e93b8ef558e54`.
- Builder: `08a0c858c083cce97f29dc928011a76a65814c6e`.
- Harness: `622e374bb6f2a8455c8f6d1fc976cbd9bd87eb4d`.
- Agent: `agent-eac6d78a03054c1f`; instance `09a8b578-67ff-42e7-8c9d-ca71c0b6ce37`.
- Installation Lock: `b43434035b135a04ce7f252bac61597bb9e580d17cb471cd2b32881dbc92de51`.
- Core receipt: `c6522f66313ad42e7c4116f6db8dcc43db3109779c669ab4240613ef695a97ce`.
- Original fixed M2 Manifest:
  `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.

The existing Builder runner was reused without source changes. It created a
fresh isolated installation, used the actual Java Provider and real Factory
HTTP/RAGFlow query, then stopped the instance and read the saved evidence with
new independent Host history authorization. All **60 checks passed**. This is
more than a wire-schema test, but is still a local technical sample, not SSO.
The two model responses were a controlled fixture, not real model evaluation.

Checks include Manifest rejection, Host revocation, service outage/recovery,
different viewer rejection, exact-receipt authorization, source-read revocation,
original answer/anchor equality and stopped-instance history. History made
**0 outbound attempts, 0 model calls, 0 new query receipts**. The original Core
database was read-only; mutations and queries used a SQLite backup. Source state
before/after is identical. Test processes stopped; shared services remain up.
An independent Maven cache was used. Builder/Harness worktrees remain clean.

The frozen history schema is unchanged:
`114397ec532e40b84975e5884457ed1de63b45c71a05652c7e8ed5c3f1f3c3c6`.
Host still issues authority; Factory only verifies it. No new approval, grant or
source activation route was added to Runtime.

## D usability delta

The reference V1.5 HTML, navigation, three-column workshop and four-step Recipe
remain unchanged. The production JavaScript now adds:

1. A primary sample action, importing explicitly synthetic material and opening
   a draft recipe with three supplied questions. Closing it starts no task.
2. A state-bound primary action: configure, produce, inspect failure, test approve,
   bind snapshot, or query. It does not promote a failed candidate.
3. The existing separate approval reason/confirmation and binding confirmation.

No frontend permission grants, automatic production, automatic approvals or
automatic queries were introduced. Sample tests do not leak into arbitrary
uploads. Existing upload/missing-test guard and disabled rule path still pass.
The UI code is therefore **not** byte-identical to the previous candidate;
`1bf631a` explicitly records this narrow, requested usability delta. User-facing
acceptance remains pending. Public zhishi still serves `d67d366`, not this delta.

## Failures and review navigation

The first cross-repository launch used a Python environment missing `lxml` and
stopped before a build/query. The retry selected the existing Factory venv for
Factory subprocesses, retaining Builder's own venv. No source fix or assertion
relaxation was needed. The first guided fixture used question phrasings outside
the exact-match controlled upstream's CASES; it failed production, not silently
passed. Defaults were aligned with the existing synthetic CASES and all attempts
remain separate. Real RAGFlow passed the final defaults independently.

`INDEX.json` separates code, contracts, tests/tools, UI/reference, docs/CI and
archived evidence. At the `1bf631a` implementation boundary, 293 of the 359 changed
paths are evidence, not runtime code. Review business modules separately; use
the indexed hashes for evidence rather than treating JSON volume as code review.
New pre-merge evidence is a separate directory. No credentials, Host authority
files, leases, cookies or raw databases are included in the public package.

Still unaccepted: P08/P43 semantics, Wiki, the other three production lines,
general PDF/Word, production IAM/SSO and authoritative source governance. No
H1b, main merge or production release is authorized by these test results.

## Reproduction

```sh
python -m pytest -q
python -m tests.run_merge_browser --guided --output /absolute/new/evidence
python -m tests.run_merge_browser --guided --native-config /existing/private/ragflow-directory --output /absolute/new/native-evidence
```

The native command uses local authorized configuration without printing it,
creates a new test index, and never reuses an existing Core database. It must not
be pointed at production credentials. Browser runs use temporary loopback ports.
