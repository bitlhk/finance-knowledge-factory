# Mainline preparation review

Status: **review candidate only; no merge, deployment, or H1b work**.
Frozen input: `160aaf51b2a54664434d5c17bc3aa95a1b75b693`.
Stable main: `bd725263e4c7d28b14fba9e665d9d180e68e84c8`.
Prepared implementation: `b906b78fed9e5d2951df68fcd858866c035806b7`.

One short-lived branch, `prep/main-convergence-160aaf5`, starts directly at main.
Its four ordered implementation commits are review units, not four additional
stacked PRs. The final documentation/CI commit adds no runtime behavior. PRs
#1-#6 and all existing source branches are untouched. Do not merge the old PR
chain together with this selected candidate: that would reintroduce experiments.

## Dependency inventory and suggested order

Original chain: main -> #1 -> #3 -> #4 -> #5 -> #6. #2 (Wiki) is an independent
fork from an older #1 baseline, not part of the frozen #6 commit. There are 23
commits between main and the frozen candidate. The complete parent/path inventory,
AST import graphs before/after and per-file SHA-256 provenance are in
`evidence/main-preparation/dependency-audit.json`.

| Unit | Commit | Scope | Prerequisites | Clean-prefix tests |
| --- | --- | --- | --- | --- |
| A | `116e69fc151e84af09895bd4a63f1372c5645945` | Public HTML anchors, bridge and evidence digest | Frozen M0 | 130 passed |
| B | `684217c0477150386fcee1fbcc79717130f405ac` | Document Core/contracts, bounded native RAGFlow transport, production adapter | A | 166 passed |
| C | `02e59a500cf2b6ca4080baae6fff731620d9dbae` | Query/session/history contracts and Host lease verification, HTTP services | A+B | 274 passed |
| D | `b906b78fed9e5d2951df68fcd858866c035806b7` | Frozen V1.5 assets and isolated document workshop | A+B | 296 passed |

Review A first, then B, then C and D. D does not import the Runtime service; C
does not import the UI. Prefix counts are cumulative, not additive. Independently
cherry-picking D without C has not been tested; the recorded executions use the
committed order above. Reviewer approval is still required before any merge.

### Removed unnecessary dependencies

| Before | After | Behavioral boundary |
| --- | --- | --- |
| Document Core/pipeline/history -> `probes.documents` | `knowledge_core.evidence` | Identical anchor and source binding semantics |
| UI -> `probes.llm.candidate_bundle` just to hash JSON | Small public evidence digest | Same canonical serialization, including finite floats; M0 hash unchanged |
| UI imports LLM coverage/lowering, gold fixtures and Flowable compiler | No `probes` imports or package in selected source | Rule requests explicitly rejected; no credential can enable them |
| Production server -> historical preview server for static helpers | `web_production.assets` | Frozen HTML/assets are byte-identical |
| History service -> Runtime service -> RAGFlow for process helpers | `m2.process_support` | No network client needed for history |
| Runtime tests -> UI production fixtures | Core-only `tests.runtime_support` | Prefix C tests run without any UI files |
| UI -> full acceptance CLI for synthetic identities | Explicit `m2.synthetic_context` | Test context only; Runtime does not issue authority |

The small M0 `rules.validate_scope`/`in_scope` functions remain shared scope
validators. They are **not** the M1 extraction/Flowable experiments, and removing
them would change the existing authorization/applicability contract.

## Unchanged results and preserved evidence

- All 229 original `evidence/` files are byte-identical to `160aaf5`, including
  failed parsing, rule extraction, rejected installation and HTTP attempts.
  Their original execution SHA/status remain historical, not this candidate's
  fresh acceptance. The large evidence diff is an archive, not new business code.
- M0 `knowledge_core/` and contracts from main are byte-identical. Runtime
  contracts and six V1.5/static UI assets are also byte-identical to the source.
- Eleven migrated business modules have identical ASTs after excluding top-level
  import statements. UI changes are separately limited to dependency removal,
  disabling rule execution, truthful code provenance and explicit test launch.
- Deterministic before/after lifecycle comparison used the same synthetic source,
  controlled transport, input, identity and clock. All 16 stored Core objects,
  candidates, validation, approval, Manifest, receipt, replay and revocation errors
  match exactly. Output digest:
  `358a8ed709fdcc94fa65e978f913fb54a1c676bcc83ee4d6372dbd178d105465`.
- Fixed M2 Manifest remains
  `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
- History schema SHA-256 remains
  `114397ec532e40b84975e5884457ed1de63b45c71a05652c7e8ed5c3f1f3c3c6`.
  The frozen filename still contains `proposed`; its separate freeze record
  remains authoritative. No schema rename or authorization change was made.

## Verification and its limits

1. The **full frozen source** passed 434 Python tests in a detached `160aaf5`
   worktree. This does not re-run real LLM, Java Flowable or RAGFlow quality trials.
2. Each A/B/C/D prefix passed in a separate detached worktree using the same pinned
   Python 3.12 test environment. The final subset has 296 tests, not a replacement
   score for the old 434. Original experiment tests remain on the frozen branch.
3. Real loopback HTTP history regression passed **16/16** against a SQLite backup
   and the previously saved Harness result for `agent-60b8171a34ef479c`. Query
   response projection matches that saved result; source database state is
   unchanged. History produced **0 outbound attempts, 0 RAGFlow calls, 0 model
   calls and 0 new query receipts**. One oversized receipt was deliberately
   inserted by test setup on the copy, never by history reads. This uses a
   synthetic Host fixture, not a new Harness installation or identity acceptance.
4. Browser regression at a temporary loopback port covered upload, four-step
   recipe, missing-test rejection, rule-disabled state, validation, test approval,
   publish gating, query, refresh without POST/reexecution, and 320/390px overflow.
   Core and page code are real; the upstream is a **controlled test client**, not
   native RAGFlow. Screenshots must not be used as new native-retrieval evidence.
5. Two preparation failures are retained: C's initial collection error from an
   omitted test helper, and the first browser fixture creating a new empty
   in-memory index client per query. Both were fixed in test plumbing, not by
   changing business assertions. Successful retries have separate records.

JUnit's 12 warnings concern `record_property` with xunit2 and are preserved.
CI runs 3.10 and 3.12; CI results are additional evidence, not real-component
acceptance. No fresh model/embedding calls or new bank data were used.

### H1a evidence linkage

The later saved `history-owner-joint-02` report has 60 passing checks and records:

- Factory `160aaf5`; Builder `7ae2a86ce25d01374c0c3635d60d28c195f80504`;
  Harness `8b9a8d0cf5a44ba6b826c77f8fbaa5d684ade1bd`.
- Agent `agent-8432b3738d2549ab`, instance
  `621c3389-49c5-48be-9f4a-a01cefcdecfb`.
- Installation Lock
  `133f83806d85fde8b26fbc662297c2ffa2416f4428633ffa0f9167208dced41a`.
- Core receipt
  `771a626b896639970b9ddc25715ff25a771b1d7f3b7812003f20e28c49f964f8`.
- Existing local workbench session, **not production SSO**. Controlled model use
  is not a new model-quality score. Review of saved evidence is not a re-run of
  Builder/Agent installation on this preparation branch.

The sanitized linkage and original report digests are in
`evidence/main-preparation/h1a-saved-linkage.json`. The earlier partial-identity
report is kept separate. Do not substitute the new agent's Lock/receipt for the
older agent used in the isolated HTTP regression.

## Merge eligibility versus production enablement

| Module | Eligible review scope | Not enabled / still requires work |
| --- | --- | --- |
| A | Native numbered-HTML evidence and contracts | General PDF/Word acceptance, other three production lines |
| B | Isolated document lifecycle, bounded RAGFlow service adapter | Production endpoint/configuration, authoritative source governance, multi-user IAM |
| C | Fixed Manifest query/session/history, current permission checks | Production Host trust/lease lifecycle and deployment review; Factory must not issue Host authorization |
| D | Existing V1.5 document workshop and Core-owned test release | Production approvals, real user grants and source activation; no rule/Wiki execution |

P08/P43 coverage/lowering, LLM extraction quality, Wiki workers, their probe
runners and the old V0.1 debug viewer are excluded from executable mainline code.
Their evidence remains. `REVIEW_REQUIRED` is not relaxed. Rule execution returns
`RULE_EXPERIMENT_ISOLATED`; M2 continues to reject non-document requests.

The existing wheel remains the M0/Core package. Runtime/UI run from a source-tree
checkout; this preparation does not claim a production service distribution.
No automatic service installation, restart, public listener or publishing job is
introduced. No imports start a service.

## Reproduction / review steps

Install `requirements-test.txt` in an independent venv. Run `python -m pytest -q`
and `python -m examples.m0_smoke`. For provenance, run
`python tools/merge_audit.py --candidate b906b78 --output /tmp/kf-audit.json`.
`tools/run_merge_prefixes.py --output <new-directory>` creates only detached
review worktrees and logs; it never changes the original worktree.

Optional UI regression (no real upstream or credentials):
`python -m tests.run_merge_browser --output <new-directory>`.
It uses the local Playwright installation/Chromium paths or the
`PLAYWRIGHT_MODULE`/`CHROMIUM_PATH` environment overrides; its temporary server
and temporary Core state are removed on exit.

Manual native preview remains opt-in and single-operator only:

```sh
python -m m2.web --isolated-test-preview --state /absolute/new/test-state \
  --private-config /absolute/existing/private-ragflow-config.json --port 61360
```

Do not point it at existing M2 state. The new preview CLI refuses reserved
61353/61357/61358/61359 ports. Runtime query/history CLIs remain unchanged; consult
the frozen H1a service docs for protocol reproduction, not for production enablement.

Before mainline merge: reviewers approve A-D scope and disabled paths, confirm CI
and evidence identities, then choose the reviewed commits/order. Before production:
separately review IAM/Host boundaries, authoritative activation, distribution,
endpoint configuration and deployment/rollback. H1b remains a separate task.
No old branch should be deleted as part of this review.
