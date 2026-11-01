# Financial HTML document quality v0.1

## Scope and compatibility

This phase covers existing HTML regulations only. It does not add PDF or DOCX
ingestion and does not change the Harness/Builder consumption contract.
`document-manifest.v0.1`, evidence responses, native anchors, permissions, and
history replay remain unchanged.

Previously published v0.1 products are immutable. They are classified as
`LEGACY_NOT_QUALITY_QUALIFIED`; the new gate neither rewrites nor revokes them.
For a new product, Factory must produce an internal content-addressed quality
receipt before creating the same outward v0.1 manifest. The receipt stays on the
Factory production side and is not a new Harness dependency.

## Frozen internal objects

`DocumentUnit` is the canonical source structure. It represents chapters,
sections, articles, paragraphs, enumerated items, and attachments with a stable
ID, parent, title path, exact source anchors, source digest, and text digest.
RAGFlow content never creates or replaces a `DocumentUnit`.

`RetrievalChunk` is an indexed search slice. It records its own digest and the
canonical unit IDs and title paths it overlaps. Several chunks may cover one
long article, but their exact source ranges must jointly cover the complete
article before the index is admitted.

`RetrievalCandidate` is a ranked result for one query. It records rank, chunk and
unit identities, the available RAGFlow similarity components, selection status,
profile, and latency. It is evaluation evidence, not authoritative source text.

`QualityEvaluation` binds a frozen test-set digest, source/index identities,
retrieval profile, actual engine identities, metrics, per-case candidate ranks,
selected evidence, expected evidence, and failure classification. Answer checks
add the actual Harness request correlation and separately classify retrieval
miss, insufficient evidence, answer fact error, and citation error.

## Source completeness

The canonical parser starts at the first explicit chapter, section, article, or
attachment marker. Publication metadata before that marker is excluded from
regulatory-body coverage. Every subsequent substantive DOM text node must belong
to a structural unit. Article sequence gaps, parser omissions, anchor mismatch,
or incomplete union mapping from retrieval chunks fail closed.

For the pinned suitability HTML, the new analyzer found 5 chapters, 49 articles,
18 paragraphs, and 51 enumerated items. Source-structure coverage and anchor
accuracy are both 100%. The old clause list omitted the five chapter headings,
which is why its parser-coverage view was only 95.93% even though all articles
were present. These are now independent measures.

## Frozen evaluation and result

The acceptance set contains 30 cases: 6 canonical, 12 paraphrases, 6 confusable,
and 6 no-answer questions. The tuning set is separate by case ID and question.
Malformed JSON, duplicate questions or IDs, missing clauses, invalid no-answer
gold, and answer cases without facts are rejected before any retrieval call.

The unmodified baseline achieved Recall@3 79.16%, Hit@1 62.50%, MRR 71.52%,
and a 100% no-answer false-positive rate. Merely expanding the candidate pool did
not improve the tuning result. The selected tuning profile uses a 50/50 hybrid
weight, a 12-candidate internal pool, deterministic structural ranking, and a
0.38 selection threshold. External v0.1 output remains capped at three evidence
items.

On the untouched frozen acceptance set the candidate achieved Recall@3 87.50%,
Hit@1 87.50%, MRR 89.58%, and a 16.66% no-answer false-positive rate. It correctly
ranked Article 22 first for the product-risk-level question, but five cases still
failed. The candidate therefore remains rejected for publication; all original
rankings and classifications are retained under `evidence/document-quality/`.

No approved RAGFlow reranker exists in the pinned setup, so a reranker result is
reported as unavailable rather than simulated.

## Publication gate

New HTML products require 100% source structure, anchors, parser coverage,
article sequence, and index-to-source coverage; 100% Recall@3 and zero no-answer
false positives; at least 90% Hit@1 and 95% MRR; every multi-evidence case passing;
and a real Harness/DeepSeek answer evaluation with complete fact and citation
accuracy. Any missing result rejects publication.

The real Harness answer comparison is not complete in this candidate. The only
installed local Agent was active, so this work did not stop it or contaminate its
conversation state. A controlled model result is not accepted as a substitute.
If the isolated real-model run shows correct evidence but wrong prose, the next
change is a separately reviewed minimal Harness answer-guard proposal; this
Factory branch will not modify Harness.
