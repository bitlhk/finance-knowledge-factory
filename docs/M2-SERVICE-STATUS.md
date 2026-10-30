# M2 service integration increment, not end-to-end acceptance

2026-10-30. Status: **IN PROGRESS**. Separate branch `feat/m2-document-e2e`,
stacked on PR4 / `784974f`. Do not merge or deploy this increment as completed M2.

## Delivered and actually executed

- New `m2.pipeline` uploads the frozen synthetic HTML to the native RAGFlow
  HTTP service. It uses new dataset/document/build identities for each attempt.
  No prior M1 index or saved answer is substituted.
- Native DOM anchors, original bytes, derived text, index/chunk hashes,
  recipe, candidate, retrieval tests, approval, manifest and binding form a
  Core-owned immutable closure. M0's existing SQLite store/policy/CAS are reused.
- Document approval is an additive, explicitly `ISOLATED_TEST_APPROVAL`
  contract, not M0 rule approval and not bank business approval. The frozen
  M0 `core.py`, schemas and old evidence remain byte-identical.
- Query checks current policy, source activation, applicability and the pinned
  manifest before retrieval and again before returning. Unknown or modified
  chunk content is rejected. Results are original quotations, not generated answers.
- The existing V1.5 UI and port 61352 were NOT replaced. There is no new M2 UI
  endpoint in this increment. No Builder install, Agent Lock or Agent UI success
  is claimed.

## Actual evidence and its limits

`evidence/m2-service-integration/attempt-001.json` through `attempt-003.json`
retain all three native runs. Each uploaded one new document, created four native
chunks (including the heading), verified three numbered clauses and retrieved
the required clause for each of the three frozen questions in top 3.
This is **3/3 fixed synthetic questions per attempt**, not 30 independent questions,
not independent semantic acceptance, and not a comparison of retrieval engines.

Attempt 001 preceded the additive-store adjustment and has incomplete code
provenance: its tracked diff did not include then-untracked files. Preserve it as
development history, not final reproducibility evidence. Attempts 002/003 include
per-file implementation hashes and actual Docker image identities. Attempt 003
is the final service-path run for this increment. Its base commit is the PR4
ancestor; its implementation map identifies the uncommitted implementation used.

Attempt 003 includes eight actual service/Core rejection checks: unpublished
candidate, missing approval, registered-but-not-effective source, mismatched
manifest, unauthorized identity, missing trusted context, revoked source read,
and actual RAGFlow API outage. For the last check, the exclusive test API container
was stopped; query returned `RAGFLOW_UNAVAILABLE`. Restarted Core replay still
returned the saved result while that API was unavailable.

Controlled unit tests additionally cover return-time revocation, another tenant,
business 403 inside HTTP 200, malformed code types, redirects, content tampering,
draft mutation, approval/validation mismatches, immutable rows and rule rejection.
These controlled cases are NOT real Harness authorization or real-user IAM tests.

All `modelCalls: 0` fields mean no **generative LLM** calls. Real local BGE
embedding was used by RAGFlow. Cost remains unknown, not zero.

During development, one frozen-M0 hash regression and one error-code preservation
test failed. The M0 change was withdrawn; a `Rejected` subclass caught as
`ValueError` was corrected. No old evidence or expected business result was edited
to remove either failure. Final regression receipt is adjacent to the native runs.

## Gates not yet complete

| Gate | Actual state |
| --- | --- |
| A01 UI upload -> native index | API/CLI path proved; browser path NOT IMPLEMENTED |
| A02/A03 original anchors + fixed retrieval cases | Real service passed, limited synthetic fixture |
| A04/A05 invalid input/content | Controlled tests passed |
| A06 native timeout/failure lifecycle | Explicit adapter rejection; real failure injection and orphan reconciliation NOT COMPLETE |
| B lifecycle and query authorization | Limited service path passed; authenticated HTTP/UI adapter NOT COMPLETE |
| C01-C03 H1a managed build/install/Lock/UI | NOT EXECUTED; no admission bypass |
| C04 H1b bank + knowledge | NOT IMPLEMENTED |
| C05 Agent stop receipts | NOT APPLICABLE yet; no Agent created |

The pipeline can leave a new native dataset after a later failed candidate stage.
It records newly created dataset/document IDs, but has no automated orphan cleanup
or crash-recovery reconciler yet. Do not expose this CLI as a multi-user service.
The test approval actor is fixed synthetic server configuration, not real IAM.

## H1 code evidence and minimal next changes

Read-only inspection of Builder `9d33295f` and Harness H0 `df7b08b` confirmed:

1. `src/finance_solution_builder/component_assembly.py:160` accepts a single
   `connection_kind`. Lines 216-217 require every selected Provider to use it.
   H1b therefore needs versioned per-Provider connection binding, not an allowlist edit.
2. `templates/local-readonly-service/.../ReadOnlyProviders.java:26` constructs all
   providers with one connection; lines 29-32 obtain a bank session and customer
   reference. H1a needs a knowledge-specific trusted authorization/session supplier.
3. Pack installation is atomic. The H0 knowledge pack also contains synthetic
   rule evaluation. M2's document-only Agent needs an evidence-only installable
   selection; it cannot silently advertise a rule tool or omit it after installation.

Next: (a) connect the unchanged V1.5 workflow to Core-owned state and explicit test
approval; (b) implement H1a's knowledge connection/supplier/classpath/qualification
and actual Lock, then query through the existing Agent page; (c) implement and test
H1b's separately bound connections. Preserve existing bank grants and scopes.
The above are remaining engineering work, not requests to redesign the platform.

## Isolation and reproduction

All eight previously stopped `kf-m1-ragflow` test containers were started for this
run and returned to stopped state. The embedding process created for this run was
terminated. Their data volumes and the three new datasets are retained as evidence;
this is not a claim of complete resource cleanup. Existing 61352, Harness and
Builder worktrees/services were unchanged.

Only start the already prepared exclusive local test stack after checking its
ownership and resources. Keep API on 127.0.0.1:19380 and embedding on its private
Docker bridge. Credentials remain in the original private probe configuration;
do not copy them into the repo or command arguments.

```bash
python -m pytest -q
python -m m2.acceptance \
  --private-config /path/to/private/ragflow-service \
  --output /path/to/new-empty-attempt-directory
```

`--verify-outage` explicitly stops only `kf-m1-ragflow_api_1` and never restarts it.
Use it only with exclusive ownership of this local test container. A successful
report is `PASSED_LIMITED_AB_SERVICE_PATH`; it never represents full M2 acceptance.

M1 semantics, PR1/PR4/PR95, public deployment, real banking approval and real user
isolation remain outside this increment. No production release was made.
