# Financial document quality final acceptance

## Decision

The independent knowledge Agent engineering path and the corrected answer-quality gate are green. PR #11 remains Draft and must not be merged or deployed without review approval.

- Normal Builder Build, managed installation, real Factory retrieval, live DeepSeek execution, stop, and independently authorized history replay passed.
- The original v0.1 evaluation remains preserved at 5 of 6. Its retained failure is `independent-no-answer-yield`.
- The v0.2 evaluation replays the same six original archives and passes 6 of 6. No gold, threshold, answer, retrieval result, or historical evidence was changed.

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

The original Core runtime-evidence object remains `6bdf78609d0311ebd3b079a42af2e93713ae412f5abe9bdd80a4c8d59daf3ba4`. The v0.2 replay created runtime-evidence object `8503d1217311b5a9471ac6076bb2ee916b2e253cfa9a9643c4995cb6e5001a5d`, answer-evaluation object `ce0dc890dffbc1ffadc54a34e0deeff34ac2f769afd45edce931f1f64c05c143`, and quality-admission object `4e3385b4aceeeb167ca35d2e9ace330cf55708fbadf39610ae1594e27c0c3084`.

It was recomputed from the immutable service Lock, model-selection digest, six original `finance-knowledge-answer.v0.1` archives, matching runtime Locks, live model-context and returned model-attempt events, six immutable Factory Core receipts, and the stopped-instance receipt. The caller no longer supplies a trusted execution label or model identity.

The v0.2 runtime evidence keeps retrieved candidates under `retrievedEvidence`. It derives `answerCitations` only from explicit references in the immutable archived answer and binds each citation to exact evidence in a verified Factory receipt. Unmatched references are retained as failures. Answer facts must occur in both the archived answer and at least one cited trusted quote. `forbiddenClaims` are now scored, including the distinction between an asserted claim and a nearby explicit negation.

This proves execution and lexical evidence association. It is not an independent semantic judge: implicit citations, paraphrased facts that do not preserve the frozen fact string, and complex linguistic negation remain outside the v0.2 claim.

## Answer and history results

All five answerable cases still return their required facts and answer citations. The no-answer case is now `CORRECT_REFUSAL`: it may cite the second and third clauses as background for the limitation, while the evaluator verifies that the archived answer makes no prohibited affirmative product-yield claim.

The replay did not invoke retrieval, a model, or a Provider. It used a database backup and the six immutable answer archives, so the original 5/6 failure remains independently inspectable. The versioned evidence is under `evidence/document-quality/final-answer-v02/`.

After the same instance stopped:

- six history reads returned the exact archived answer, Manifest, Factory receipt, Build, and Instance;
- `runtimeLeaseReused` was false and all temporary history leases were reclaimed;
- disabling the independent history authority produced six `403 HISTORY_FORBIDDEN` responses;
- Factory Core object counts stayed at 37 before and after history replay, so replay created no query receipt;
- no model or Provider was run during replay.

The full local evidence is under `/home/ubuntu/outputs/knowledge-quality-pr11/final-acceptance`. Stable hashes and receipt digests are recorded in `evidence/document-quality/final-acceptance-20261101.json`.

## Verification

- Knowledge Factory: `369 passed`.
- Builder impacted suite: `305 passed, 7 skipped`.
- Builder archive/history suite with the actual candidate dependency closure: `71 passed`.

## Review conclusion

The final publication review found and fixed one correctness defect: runtime used to discover a quality profile by scanning every PASS admission for a Candidate. A later PASS could therefore make an existing Manifest ambiguous or change its retrieval behavior. Quality publication now atomically records one internal, immutable admission link keyed by the exact Manifest digest. Runtime resolves only that link. Existing v0.1 Manifests remain on the baseline path and cannot be retrofitted after publication; a later PASS is available only to a future release.

The external `document-manifest.v0.1` bytes, query authorization, source checks, receipts, and stopped-history contracts remain unchanged. Regression coverage verifies the legacy path after quality enrollment, exact Manifest/Candidate/Admission linkage, rejection of an attempted retrofit, and stable retrieval behavior after a second PASS with a different profile.

The implementation is suitable for Ready for Review. The normal independent-Agent path, trustworthy runtime correlation, retrieved-evidence/answer-citation separation, immutable publication admission, and 6/6 replay over the original archives are demonstrated. No published product or external v0.1 query/history contract changed.

This closes retrieval optimization for the current synthetic regulatory document. A future openJiuwen Python Evaluation Worker is a separate design and must not be added to this PR.
