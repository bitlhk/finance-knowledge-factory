# Financial document quality phase 2

Status: Draft candidate only. No product was merged, deployed, or substituted for an existing v0.1 product.

## Production wiring

The quality path is now separate from legacy document publication:

1. HTML is parsed into canonical structural units and exact source anchors.
2. RAGFlow chunks are mapped back to canonical articles. A long article may span chunks, but the union must cover the full normalized article text.
3. A versioned quality profile and immutable test set are registered in Core.
4. Core recomputes retrieval metrics from per-case candidates. Caller-supplied aggregate metrics are not accepted.
5. Core recomputes answer fact and citation checks from raw answers and the immutable gold set.
6. Core recomputes admission from source, index, test set, profile, retrieval evaluation, and answer evaluation digests.
7. Once a candidate is enrolled in quality evaluation, legacy `publish_document()` fails with `QUALITY_ADMISSION_REQUIRED`. `publish_quality_document()` accepts only a matching PASS admission.
8. A quality-admitted manifest remains `document-manifest.v0.1`. Runtime authorization, source currency, receipts, and history contracts are unchanged. Runtime retrieval resolves the pinned profile from the admission object; old manifests without admission continue using the baseline path.

## Five frozen failures

The original 30-case gold was not modified.

| Case | Root cause | Change | Regression |
| --- | --- | --- | --- |
| Definition paraphrase | Article 2 was raw rank 3, then removed by a global threshold | Definition-shaped evidence receives a deterministic semantic-shape rank; filtering records the reason | Article 2 selected at rank 1 |
| Online process paraphrase | Article 14 was raw rank 6, then removed by the same threshold | Bounded terminology normalization maps mobile channel wording to online/Internet wording | Article 14 selected at rank 1 |
| Insurance mismatch | Article 38 trailed Article 37 by 11 bps | Action questions prefer an explicit required action over a disclosure list | Article 38 selected at rank 1 |
| Five-year comparison | One retrieval returned only Article 17 | A comparison is decomposed into bounded independent evidence questions and fused; no answer facts are added | Articles 17 and 29 both selected |
| Highest-return no-answer | Article 13 shared product/return words but did not support a product comparison | Answer-type support requires named comparative evidence | No evidence selected |

The four recorded stages are `retrieved`, `ranked`, `filtered`, and `selected`. Each candidate records scores, clauses, decision, and reasons.

## Results

| Set | Status | Recall@3 | Hit@1 | MRR | No-answer false positive | Average latency |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Existing 30, baseline | Historical baseline | 79.16% | 62.50% | 71.52% | 100% | 88 ms |
| Existing 30, v0.2 | Regression pass | 100% | 100% | 100% | 0% | 51 ms |
| Personal-loan first blind | Failed, then used for diagnosis | 100% | 90.90% | 95.45% | 100% | 48 ms |
| Personal-loan recheck | Regression only, not relabeled blind | 100% | 100% | 100% | 0% | 57 ms |
| Customer-service next blind | Failed, then used for diagnosis | 80% | 80% | 80% | 100% | 64 ms |
| New product-policy independent blind | Independent pass | 100% | 100% | 100% | 0% | 20 ms |
| Managed candidate recheck | Same new source and new managed index | 100% | 100% | 100% | 0% | 21 ms |

Blind failures remain in evidence. They were not overwritten or presented as independent passes after adjustment.

## Real Harness and DeepSeek status

A new isolated Core database, RAGFlow dataset, candidate, and managed tenant configuration were created. Existing Agents and published products were not stopped or changed.

Real answer evaluation is **not complete**:

- The independent knowledge template reached normal Builder component admission and failed with `COMPONENT_MULTI_CONNECTION_HOST_REQUIRED`. Its generated plan contains `providerConnections`, while its host support omits `provider-connections.v1`.
- The customer-manager template was attempted with isolated CRM and product sources, but Builder rejected the CRM + product + knowledge selection with `COMPONENT_SELECTION_REJECTED` before Build.
- Both attempts failed before Agent start and before a DeepSeek request. They are not model failures and are not counted as answer evaluations.

The Core admission for the managed candidate is therefore `REJECT`. Its only failed check is `realHarnessAnswerEvaluation`. No quality-protected product was published.

Minimal follow-up belongs in Builder/Harness, not this PR: align the independent knowledge host feature declaration with its generated multi-connection plan, and admit the already designed customer-manager knowledge module combination. Then rerun the same fixed candidate and answer set. No Factory contract change is required by the observed failures.

## Compatibility and security

- Existing v0.1 manifests, bindings, query responses, source authorization, and replay are unchanged.
- Quality profile resolution is server-side from an immutable PASS admission; clients cannot select or alter it at query time.
- Quality enrollment makes legacy publication fail closed.
- Source/index/profile/test/retrieval/answer digests are all bound in the admission object.
- The isolated evaluation snapshot is not discoverable from the existing workbench and was stopped with its own subprocesses.
- Stop and history replay for a quality-admitted product remain unverified because no real quality Agent could be installed. Existing lifecycle regressions are still run, but they do not substitute for that missing acceptance.
