# H1a dependency audit and non-destructive convergence

Checked 2026-10-30 against GitHub PR metadata and local imports. This is a plan,
not permission to merge, enable production, or rewrite historical evidence.

## Fixed identities

| Line | Commit | Parent/base | Gate |
| --- | --- | --- | --- |
| M0 main | bd725263e4c7d28b14fba9e665d9d180e68e84c8 | frozen M0 | reference implementation |
| PR 1 | a91add94038d03f6c46aa067135b98b99cd7f85a | main | semantic quality not accepted |
| PR 2 | 74b8438754297495e9e5c8913d600876700901b7 | feat/m1-component-probes | Wiki experiment, Draft |
| PR 3 | c385a30c0cb3921bf3ea012306049a2df1d7967b | feat/m1-component-probes | historical evidence viewer |
| PR 4 | 784974f35b7bc2eb105d3f6137c6e5ad88330d02 | feat/web-preview-v01 | V1.5 production UI candidate |
| PR 5 | b7c0e99257f3988631e9359d3f4e7a2c0ed5f1a6 | feat/web-production-v02 | isolated document/Core service |
| PR 6 deployed baseline | c2939742f211a1ed363dc792d3602d0098765a04 | feat/m2-document-e2e | isolated web closure, not Agent |
| Harness PR 96 baseline | bd7244b3adf76e172d8cc37ef1a97bf5d4ccd727 | feat/knowledge-provider-probe | evidence-only pack, H1a blocked |
| Builder candidate base | 9d33295f74ff663c16579febd120b586c791280f | feat/knowledge-h1a-host | own worktree, not production |

PR base names do not guarantee that a child contains the current tip of its base.
Before any merge, compare actual ancestry and the complete file closure; do not
infer inclusion from the table. Do not rebase/squash historical runs into new SHAs.

## Source-level dependency closure

| Module | Actual dependency | Consequence for separation |
| --- | --- | --- |
| `knowledge_core/core.py`, contracts, rules | frozen M0 | no rewrite required |
| `knowledge_core/documents.py` | `probes.documents.anchor_bridge.verify_bridge` | document Core cannot be extracted without this verified anchor contract |
| `m2/pipeline.py` | native HTML locator, anchor bridge, Core contracts | include exact source anchors and contract tests before document service |
| `m2/ragflow.py` | Core rejection semantics, native HTTP API | isolated adapter, no asset authority |
| `web_production/engine.py` | document anchors plus `coverage_recipe`, `semantic_v2`, `verified_lowering`, `linked`, Flowable compiler, `policy_gold`, `run_coverage` | UI is not presently an independent document-only package; top-level imports retain experiment dependencies even when rules are disabled |
| `web_production/server.py` | `web_preview.server.checked/BASELINE_SHA` | preserve baseline validation helpers before archiving the historical viewer |
| `m2/web.py` | Production, Core and fixed synthetic identities from `m2.acceptance` | isolated single-operator host, not real IAM |
| `m2/harness_runtime.py` | DocumentCore, authenticated Host lease resolver | consumes a published binding; cannot produce/approve/activate/grant |
| Harness Knowledge Provider | managed factory, independent grants/session, fixed binding | cannot use a bank session or browser identity |
| Builder local Host | component admission, preparation SPI, collector qualification, experience tickets | H1a must pass all these, not merely an HTTP Provider test |

## Proposed merge order (not executed)

1. Extract the tested source-anchor and bounded protocol helpers with exact tests
   and provenance. Remove their dependency on experimental runners only in a
   separately reviewed small change; keep archived evidence bytes unchanged.
2. Admit the V1.5 UI shell and production lifecycle after separating optional rule
   execution from required document imports. Preserve the historical viewer as an
   optional evidence tool, with one baseline checker, not two maintained product UIs.
3. Admit document Core/RAGFlow and its consumption adapter after the H1a installed
   Agent gate. Keep test approval and synthetic authority explicitly isolated.
4. Harness/Builder are reviewed in their own repositories with fixed paired SHAs.
   H1b and M1 semantic/Wiki acceptance remain independent.

No new stacked branch, branch deletion, PR closure, retarget, merge, or production
deployment is part of this audit. Continue on PR 6/96 and the existing Builder
worktree. Port 61353 stays on c293974; new consumption checks must not replace it.

## Evidence identity rules

- Keep the original c293974 production run and Manifest
  `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
- New adapter and build attempts record their own source digests and commits.
- Core protocol tests are not Agent tests. Installation preparation is not runtime
  registration. Model-controlled tool selection is not established by direct calls.
- No release claim until real Builder Lock, existing Agent UI, negative cases,
  cross-scenario regression and correlated stop/history evidence all exist.
