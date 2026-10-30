# M1 semantic extraction and verified lowering

Date: 2026-10-30. Parent: `b9a53bfc2e9a402f08acbcd4f0d4cdf142774222`.
Status: **engineering candidate; M1 acceptance NOT passed; PR #1 remains Draft**.
No M0, UI, Harness, model catalog or deployed service changes. No additional
pipeline, rule-language operator, approval or production Manifest was introduced.

## What changed

1. [Engineering review](M1-P43-P08-ENGINEERING-REVIEW.md) is now included for public
   review. Its 45 tests were existing targeted regressions, NOT 45 new tests.
2. `coverage_gold_v2.py` adds the P43 application trigger as PRECONDITION/MANUAL,
   makes the P08 extended branch an exception to the general bound, and records
   reviewer identity, source basis and post-observation provenance. The reviewer
   is Codex at the user's request, not an independent credit expert or approver.
3. `semantic_v2.py` excludes `predicate` and `appliesWhen` from model output.
   A proposed numeric unit does not grant execution authority.
4. `verified_lowering.py` generates predicates from complete, source-backed,
   bounded templates and a trusted engineering field/unit registry. It rejects
   unsupported arithmetic, incomplete statements, ungrounded fields/constants
   and process prerequisites disguised as numbers. It has no P43/P08 ID branch
   and imports no gold. Different supported thresholds use the same template.
5. `coverage_review_v2.py` reports semantic errors, representation differences
   and unverifiable items separately. Multiple meanings can share one unit when
   their conditional relationship is independently checked; this is not a
   blanket exemption for merged text. No fixed number of output rules is used.
6. Immutable evidence binds original HTML, anchor sidecar, recipe, actual client
   request/response, gold, semantic output, lowering receipt, IR, DMN, model
   parameters and engine receipts. Resealing modified formulas does not pass
   replay verification. This is M1 evidence, not an M2 publication mechanism.

Old v0.1 gold, eight attempts, 0/8 automatic assessment, 24/30 execution checks
and original report bytes are unchanged. `retrospective.json` is supplementary
review, not a new model experiment or a replacement score. Legacy branch quotes
are left absent rather than invented by the adapter.

## Frozen real-model experiment

Four serial calls, one each for P43, P08, P13 and P41. P43/P08 are development
clauses already examined. P13/P41 were frozen as new held-out clauses before
these calls, with no prompt tuning or retries afterwards. They are not an
independent human blind test. Gold and expected answers were not sent to the model.

Connection: existing authorized Volcengine `deepseek-v4-flash` catalog entry.
Actual client parameters: temperature 0.1, top_p 1, max_tokens 4096,
thinking.type disabled, stream false. Four calls completed; strict JSON 1/4,
complete bounded JSON fences 3/4, schema accepted 4/4. No salvaging of incomplete
output or semantic repair. Reported tokens 5,636; summed request durations
11.579 seconds. Cost remains unknown. Responses still contain two backend names;
backend equivalence and billing are not established.

| Attempt | Observed result | Acceptance boundary |
| --- | --- | --- |
| P43 | All eight expected text meanings located; application trigger retained; half bound UNSUPPORTED; short comparison proposed | Process dependencies emitted as requires; merged process relations remain unverified; whole clause not accepted |
| P08 | All seven expected meanings located in four units; five-year and extension statements retained as MANUAL | Qualifier used as branch identifier, external dependency on extension incomplete; no verified executable rule emitted |
| P13 | Two meanings located | Additional requires edge needs review, not automatic rejection of source facts |
| P41 | Two meanings located | Kind difference and direction/meaning of follow-up edge need review |

The 19 located atomic text meanings are **anchor coverage only**, not 19 approved
business meanings. No complete clause received automatic coverage acceptance.
The schema removes model-written formulas by construction; that does not prove
arbitrary semantic extraction correct or justify a model-quality ranking.

### Frozen diagnostic mistakes and separate addendum

The frozen v0.2 checker classified P08's qualifier-only branch quote as a definite
wrong branch, although it did not explicitly name the consumption branch. It
also failed to normalize a reversed symmetric alternative edge in P43.

Both initial outputs remain intact. `coverage_review_addendum.py` v0.2.1 produces
a separate post-observation analysis: a qualifier that does not establish the
subject is UNVERIFIABLE; an explicit opposite purpose is still SEMANTIC_ERROR.
Symmetric direction alone is not a missing relation. Other uncertain relations
remain blocking. All four addendum results are REVIEW_REQUIRED, not new passes.
No model call was added to obtain these diagnostics.

## Execution results must not be combined

| Track | Results | Actual Flowable calls | Meaning |
| --- | --- | --- | --- |
| Original governed candidate | 4/10 expected outcomes; six REVIEW_REQUIRED versus frozen numeric expectations | 0 | Full requires dependencies retained; candidate is not accepted |
| Separate template numeric proof | 10/10 | 5; other five input/scope guards | Source-backed E<=O works as a numeric subcondition; does NOT clear original dependencies |
| Existing Flowable regression | 53/53 | 37; other 16 guards | Prior supported IR semantics retained |

The numeric-proof artifact is explicitly named `TEMPLATE_NUMERIC_SEMANTICS_ONLY`.
It uses the actual model's located short-term statement and deterministic
template mapping, then checks a separately identified numeric assertion. It has
a different IR/compiled identity, refers to the original bundle digest, preserves
the original governed projection digest, and keeps wholeClauseDecision at
REVIEW_REQUIRED and publicationAllowed=false. No archived dependency was deleted
and no old candidate score changed. This is a diagnostic proof, **not the missing
end-to-end acceptance**; it cannot be installed as an approved business rule.

## Technical verification

- Python: **262 passed**, including the prior 227 and 35 new focused tests.
- New tests cover model-supplied formulas, wrong operands/constants/boundaries,
  unsupported half calculations, process-as-math, wrong purpose, partial anchors,
  unresolved prerequisites, merged meanings, diagnostic distinctions, evidence
  tampering, frozen attempts and exact engine/compiled identity associations.
- Existing 53-case actual-engine regression was rerun. Sanitized request,
  response and exit status: `evidence/m1-lowering-flowable-regression/`.
- Batch-specific original/diagnostic engine receipts and SHA indexes:
  `evidence/m1-verified-lowering/`. No reference-engine fallback.
- CI results are checked after push, separately from local results. No claim
  that Python CI makes fresh model calls.

## Known limits and next gate

The lowering registry currently supports two deliberately narrow Chinese source
templates: a bounded field comparison and a purpose-specific duration bound.
It is not a general semantic theorem prover. A standalone ten-year phrase lacks
enough bound subject/qualification evidence for this compiler and remains
unverifiable. Context outside the numeric statement is retained in the full
source and semantic record; numeric agreement never establishes full compliance.
Whole-month conversion is a POC input contract, not a universal calendar rule.

Before M1 acceptance, process prerequisites versus numeric dependencies and the
P08 subject/default/exception relationships still need verifiable normalization
or explicit reviewed bindings. Review must never delete an unresolved dependency
from an existing rule just to make it execute. Freeze revised gates before any
further small model batch; preserve this batch's failures and diagnostic errors.

Web Preview V0.1 remains a separate subsequent task using the frozen V1.5 layout.
The managed Harness Knowledge Provider/Builder/Lock/tool-call probe remains an
independent pending delivery, not something these local probes prove. Wiki PR #2
is untouched; no production merge, deployment or M1 completion is claimed.

## Reproduction

Offline evidence/regression checks:

```bash
python3 -m pytest -q
python3 -m probes.flowable.run
python3 -m probes.flowable.run --request evidence/m1-verified-lowering/engine-request.json
python3 -m probes.flowable.run --request evidence/m1-verified-lowering/addendum/engine-request.json
```

The governed candidate command intentionally returns a nonzero exit for the six
frozen mismatches. Do not suppress it or call the diagnostic command its retry.
`run_lowering freeze/run` is for a new explicitly authorized experiment directory,
not rerunning or overwriting this saved batch. Credentials must stay in the
managed connection/in-memory process environment and never enter the repository.
