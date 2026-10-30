# M1 round 4: clause coverage and immutable candidate evidence

Date: 2026-10-30 (Asia/Shanghai). Parent: `8c56cb3`.
Status: **engineering changes tested; M1 semantic acceptance NOT passed**.
PR #1 stays Draft. No merge, publication, production deployment, M0 contract or
interpreter change, UI change, Harness change or employee-agent configuration change.

## Scope and frozen experiment

Two separate qualities are now checked: complete clause coverage/relationships,
and correctness of independently executable subconditions. A MET subcondition
never creates a whole-clause MET or permission to extend a loan.

- `coverage.py`: closed clause units/relationships, quote checks, independent
  semantic-span oracle, bounded IR projection. No fixed rule-count requirement.
- `coverage_recipe.py`: field meanings, units, expression whitelist and source
  budget. No expected branches, gold outputs or per-case instructions in prompts.
- `coverage_gold.py`: separate engineering oracle, not a business-approved legal
  interpretation. Model receives source and generic recipe, never this oracle.
- `candidate_bundle.py`: hashes original bytes, source/anchor sidecar, recipe,
  actual request/response, coverage, gold/assessment, IR, DMN and execution state.
  Re-sealing a mismatched response, source, projection or DMN still fails checks.
- `archive_coverage.py`: append final batch-specific receipts; pending snapshots
  remain intact. These are evidence packages, NOT M2 publication Manifests.

Frozen **8 calls**, P43/P08/P09/P12 twice, interleaved in that order. P09/P12 were
not used to tune this recipe, but the same engineering author prepared their gold;
do not describe them as independently human-blinded acceptance. Recipe, gold,
implementation files, original source and requests were frozen before calls.
No prompt or oracle change after seeing responses; no retry or model re-grading.

Managed connection remains the existing Volcengine DeepSeek connection. Only
loopback `models.list` read RPC was used; key existed in process memory/child
environment only, never in evidence or CLI arguments. Actual client parameters:
`deepseek-v4-flash`, temperature 0.1, top_p 1, max_tokens 8192, thinking disabled.
This is a new, larger output budget than round 3, not an equal-parameter A/B test.
Response identifiers still include `deepseek-v4-flash-0731` and
`deepseek-v4-flash-ga-260731`; backend equivalence remains unknown.

## Actual results

| Measure | Result | Meaning |
| --- | --- | --- |
| Model requests | 8/8 completed | Not semantic correctness |
| Original strict JSON | 1/8 | Other seven retain single-fence raw responses |
| Coverage contract processing | 7/8 analyzed, 1 rejected | P43-1 claims executable units with null predicates |
| Frozen automatic coverage oracle | 0/8 accepted | Mix of actual errors, missing structured links and representation differences |
| New executable checks | 24/30 expected outcomes; 6 failures | All 30 handled by guards; **0 actual DMN evaluations** |
| Existing real Flowable suite | 53/53 | 37 engine evaluations, 16 guards; separate regression, not new extraction success |
| Python regression | 227 passed locally | Includes original regressions and new mutations, bundles and retained-response replay |
| Usage | 22,812 upstream-reported tokens; 44,704 ms sum of request processing | Cost unknown, not zero; wall time is not a price estimate |

All new automatic scores are retained, including the nonzero Java runner exit
for six failed checks. The previous three rounds and their scores are unchanged.
There is **no unsafe MET in the retained executed cases**; this is not a proof
that all possible inputs to the rejected models are safe.

## Findings: actual errors versus oracle limitations

| Attempt | Evidence-based interpretation |
| --- | --- |
| P43-1 | Marks preconditions executable with null predicates; rejected before projection. Its raw response also uses `< 12` for the one-year boundary and substitutes literal zero for half of the original term. These are actual errors, not just different unit naming. |
| P43-2 | Short-term predicate and inclusive boundary are correct. However, consent becomes `extension_months == 0`, and the unsupported half-term formula becomes a zero ceiling. Its `requires` chain also blocks the otherwise computable short-term condition; 6/10 corresponding checks fail. |
| P08-1 | Consumption/general-business thresholds and purposes are correct. Extended-term qualification is retained together as a manual unit, not omitted from the text. No separately machine-linked extended ceiling is produced. Exact unit decomposition/type requirements contribute to the automatic failure. |
| P08-2 | Extended 120-month ceiling explicitly depends on the cash-flow qualifier and national provisions. This is an improvement in the retained representation, not a full acceptance. `general` remains only in quoted text rather than a separate constraint; combined qualifier units and taxonomy differences also fail the strict oracle. |
| P09-1/2 | National provisions remain in the negotiation quote but are not an independently typed EXTERNAL dependency. Principle taxonomy/relationship conventions differ. These outputs remain manual and do not invent an executable rate rule. |
| P12-1/2 | All six enumerated requirements are retained as manual units. The last is MANUAL/PRECONDITION rather than EXTERNAL/REFERENCE. This is principally a classification/governance distinction, **not evidence that all six facts were lost or false**. |

The oracle deliberately does not infer equivalence from natural language. Its
semantic-span matching and canonical AST comparison are inspectable, but its
one-unit-per-gold mapping, enum categories and exact relationship graph can reject
valid merged representations. For example, P43 management and classification
can be quoted together, and P08 cash-flow/extension qualifiers can be grouped.
These failures must go to review. **0/8 automatic acceptance is not 8/8 business
answers wrong.** This limitation is not solved by relaxing old results or passing
everything marked REVIEW_REQUIRED. The gold also needs a separate reviewer to
confirm its coverage boundary, including treatment of application triggers.

## Safety and evidence closure

`requires` dependencies are transitively retained as unresolved evidence; even
an executable prerequisite is not assumed already satisfied. Existing M0
`if unresolved: REVIEW_REQUIRED` semantics are unchanged. Business-process
prerequisites stay in the coverage asset and results are SUBCONDITION_ONLY,
with wholeClauseDecision=NOT_EVALUATED and publicationAllowed=false.

Tests demonstrate that wrong cash-flow branch links fail despite all REVIEW
outcomes, swapped fields fail, fabricated executable formulas fail the gold,
unknown quotes and relation IDs fail, source truncation is refused, and missing
or changed bundle components fail. Rejected P43-1 has raw request/response and
error evidence, **no invented IR or successful candidate bundle**.

Seven execution-time bundles and seven appended final bundles are retained.
Every final receipt checks the global request, case IDs, compiled digests and
expected/actual results. Final receipts explicitly retain zero engine calls.
[Evidence index](../evidence/m1-round4/INDEX.json) hashes 29 exported JSON files.
Checksums prove retained consistency, not a digital signature or business approval.

## Unchanged scope and separate work

- HTML remains the demonstrated native-source bridge. PDF 52/53 and 190/193
  region checks and Word conversion/location failures remain in round 3, not
  erased or reclassified. No new format-support acceptance was granted.
- Q01/Q25 retrieval misses remain. No retrieval retuning or claim that an
  irrelevant result becomes authoritative evidence.
- RAGFlow source-level ACL, authority activation and atomic release are still
  M2 work; Provider/Lock integration is still M3.
- Wiki compilation is in **separate branch `feat/m1-wiki-worker-probe`**, not
  this PR. Its own evidence must not be counted as clause-rule acceptance.

## Reproduce without new model calls

```bash
python3 -m pytest -q
python3 -m probes.flowable.run
python3 -m probes.flowable.run --request evidence/m1-round4/engine-request.json
```

The last command intentionally exits 1 for retained semantic-check failures and
records all 30 guard outcomes. Do not change expected values to make it green.
New model batches require a new output directory; existing attempts cannot be
overwritten. CLI `freeze` then `run` is documented by `run_coverage --help` and
expects the already authorized managed connection in environment variables.

## Next decision

Do not merge M1 as accepted. The next small revision should separate semantic
identification from executable lowering, rejecting invented unsupported math;
review the oracle's representation constraints separately before freezing another
batch. Preserve this batch. Do not expand Rule IR or weaken unresolved guards.
M1 cannot be called closed until full-clause coverage and a genuinely extracted
executable subset both pass their respective checks.
