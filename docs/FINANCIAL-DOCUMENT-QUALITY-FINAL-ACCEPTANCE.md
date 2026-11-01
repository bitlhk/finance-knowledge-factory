# Financial document quality final acceptance

## Decision

The independent knowledge Agent engineering path is complete, but the answer-quality gate is not fully green. PR #11 must remain Draft and must not be merged or deployed.

- Normal Builder Build, managed installation, real Factory retrieval, live DeepSeek execution, stop, and independently authorized history replay passed.
- The fixed answer set passed 5 of 6 cases under the current Core answer-evaluation logic.
- The retained failure is `independent-no-answer-yield`. The model refused to invent a product-yield ranking, but the retrieval result included boundary clauses. The current evaluator derives `citedClauses` from every retrieved evidence item and then requires no citations for a supported refusal. No gold or threshold was changed.

## Fixed blockers

1. `COMPONENT_MULTI_CONNECTION_HOST_REQUIRED` was caused by the knowledge Host support declaration omitting `provider-connections.v1`, even though the installed Provider had a real connection plan.
2. The independent knowledge scenario was missing from normal scenario startup and was incorrectly subjected to bank preflight.
3. The composed Builder branch omitted the knowledge-answer metadata projection used by the stopped-history path. The restored projection verifies archive digest, Agent/Instance, service/runtime Lock, actual capability completion, and Factory receipt binding before reporting `RECORDED`. It does not grant disclosure permission.

The customer-manager three-Provider `COMPONENT_SELECTION_REJECTED` path was not modified.

## Fixed execution identity

| Item | Value |
| --- | --- |
| Knowledge runtime commit | `e79d55599b95848592d980b1c5c623dd8bda0267` |
| Builder normal-Build commit | `7b9bc0ad566dc9ee1727f69611d0569c4d95da96` |
| Builder stopped-history commit | `9a822259682b4915ade5c33dd92022e68f567c62` |
| Harness commit | `1773f63d99e568f4e5fc806a10d5a31dabfd533e` |
| Build | `agent-3ebaa283026f4d35` |
| Instance | `bdb603f4-8eef-4280-9114-5cb3909de331` |
| Installation Lock | `fa6cd409b2af480b227721cd1fde7b0f5aa2df5c592daf3a06ac0a56523bdaa1` |
| Runtime Lock | `ceaaca6ee1eaedcc4e41cf6cf1546c634ebf40575c705114c08cf0133cdf1838` |
| Manifest | `5eb19bb662f311cc91ed5cef0fac20bfbd3b75a9d45c5a7d69b46e24ae570d1b` |
| Model | `model-ea-002` / `deepseek-v4-flash` |

## Trusted runtime evidence

Core created runtime-evidence object `6bdf78609d0311ebd3b079a42af2e93713ae412f5abe9bdd80a4c8d59daf3ba4` with verification `CORE_CORRELATED_HARNESS_ARCHIVE`.

It was recomputed from the immutable service Lock, model-selection digest, six original `finance-knowledge-answer.v0.1` archives, matching runtime Locks, live model-context and returned model-attempt events, six immutable Factory Core receipts, and the stopped-instance receipt. The caller no longer supplies a trusted execution label or model identity.

This proves execution association. It does not turn lexical fact matching into an independent semantic judge. The v0.1 evaluator also does not currently score `forbiddenClaims`; this remains an explicit quality limitation.

## Answer and history results

Five answer cases returned the required fact and clause. The no-answer case correctly refused to rank product yields but remains a strict gate failure for the citation-model reason described above.

After the same instance stopped:

- six history reads returned the exact archived answer, Manifest, Factory receipt, Build, and Instance;
- `runtimeLeaseReused` was false and all temporary history leases were reclaimed;
- disabling the independent history authority produced six `403 HISTORY_FORBIDDEN` responses;
- Factory Core object counts stayed at 37 before and after history replay, so replay created no query receipt;
- no model or Provider was run during replay.

The full local evidence is under `/home/ubuntu/outputs/knowledge-quality-pr11/final-acceptance`. Stable hashes and receipt digests are recorded in `evidence/document-quality/final-acceptance-20261101.json`.

## Verification

- Knowledge Factory: `366 passed`.
- Builder impacted suite: `305 passed, 7 skipped`.
- Builder archive/history suite with the actual candidate dependency closure: `71 passed`.

## Review conclusion

The implementation is suitable for continued Draft review. The normal independent-Agent path and trustworthy runtime correlation are demonstrated. PR #11 is not merge-ready because the frozen answer gate is still 5/6 and the semantic/citation distinction is unresolved.

The smallest follow-up is to archive explicit answer citation references separately from retrieved evidence and have Core evaluate those references. That change must preserve the retained failure until independently re-evaluated; it must not alter the gold set or lower the threshold.
