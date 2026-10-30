# M1 second probe round (2026-10-30, Asia/Shanghai)

Status: **in progress, Draft PR only; not M1 acceptance, not deployed**.
Local Python regression: **154 passed**, including the original 111 M0 tests.
Evidence: [second-round per-attempt records](../evidence/m1-round2/).
V1.5 UI and the M0 business kernel/contracts remain unchanged. Previous evidence
in `evidence/m1-initial/` is retained byte-for-byte.

## 1. Same-source HTML comparison

Real upstream RAGFlow `v1.0.0-rc2`, commit
`ac29b4b29928ca65d3efca19b6cfae3f86069b81`, compiled using Go 1.27.3 with
CGO disabled for the **HTML-only** library probe. The original parser package
is imported; no parser code was copied or substituted. This is NOT a deployed
RAGFlow server, embedding service, database, or search index. PDF and Office
native backends are not covered by this no-CGO build.

Both parsers consumed the exact previous HTML bytes, SHA-256
`d091d80052322f3c933f846dab94078bc7fb25b08565c4fa20530e68e37cb5fa`.
Source: [official Ministry of Transport republication](https://credit.mot.gov.cn/zhengcefagui/202408/t20240807_4147084.html).

| Measurement | Docling 2.145.0 | RAGFlow pinned HTML parser |
| --- | --- | --- |
| Raw text items | 36 | 3 |
| Separate native target-clause locations | 0/5 | 0/5 |
| Native DOM source anchors | Absent | Absent |
| Shared structural adapter: clauses | 52 | 52 |
| Round-tripped original DOM text anchors | 101 | 101 |
| Shared BM25 diagnostic: top-1 | 23/30 | 23/30 |
| Shared BM25 diagnostic: top-3 | 26/30 | 26/30 |

The common adapter uses original text-node XPath, Unicode character ranges,
source hash and exact quotes, including `<br>` tail text. It verifies every
anchor against the saved original and refuses clauses whose text the parser
omitted. These are **adapter-created HTML anchors**, not native parser anchors,
PDF page numbers, or offsets in a regenerated document.

The thirty questions and gold clause labels were authored before running this
retrieval diagnostic; they are separately versioned and were not changed to
improve scores. This is not an independent blind test. The ranker is identical
on both sides (`rank-bm25==0.2.2`, Chinese/alphanumeric bigrams, k1=1.5, b=0.75,
epsilon=0.25). **Do not call these RAGFlow hybrid-retrieval scores.** Failed
queries are included. No embedding model, reranker or LLM judge was used.

Conclusion: replacing Docling with RAGFlow alone does not solve this HTML
structure problem. A small shared locator adapter works on this source. This
does not select a winning general parser. HTML/Word/PDF format policy, tables,
cross-page evidence and a real RAGFlow retrieval baseline remain open.

## 2. Linked extraction to executable IR

Added a probe-only extraction contract. Each rule binds its own predicate,
`appliesWhen`, trusted scope, source quotes, exceptions and unresolved references.
The converter reuses the existing Rule IR validator, maps non-applicability to
`NOT_APPLICABLE`, preserves unresolved references, rejects unknown fields,
incorrect types, changed source hashes and unconfirmed scope changes. No rule
is approved or published by the converter.

Four new synthetic inputs were frozen before the model calls; the old C01-C08
batch and scores were not altered. There was one preparation failure before any
model request: the probe incorrectly used the no-float asset digest for request
parameters containing temperature. Request-byte hashing fixed the probe, not M0.

Actual new calls: **4/4 returned; strict JSON compliance 1/4**. E02-E04 returned a
single Markdown JSON fence and the original attempt records remain failed.

A separately versioned offline decoder accepts only one complete `json` fence
or pure JSON. It rejects preambles, trailing text, duplicate keys and invalid
JSON; it does not repair JSON or modify values. Reprocessing the four retained
answers made **zero new model calls**. This additional analysis does not replace
the original 1/4 format result.

- Four retained answers converted into six source-bound Rule IR candidates.
- E01/E02 had no unresolved conditions: unnecessary-review count 0/3 rules in
  this tiny expanded batch, not a statistically valid improvement estimate.
- E02 binds A to 12 months and B to 36 months; evaluating the other category is
  NOT_APPLICABLE. Missing and unknown categories are tested separately.
- E03/E04 retain the missing classification/reference evidence and remain
  REVIEW_REQUIRED, never MET.
- Fourteen frozen boundary/category checks passed in real Flowable: **8 engine
  evaluations, 6 guards for unresolved references**. No reference fallback.

These are synthetic extraction/compilation probes, not a real-document end-to-end
production acceptance. Scope and field registry are trusted test inputs. The
converter cannot prove completeness of arbitrary natural-language exceptions;
independent semantic review remains necessary before publication.

## 3. Flowable differential and failure checks

- 53/53 gold cases: previous 28 plus 25 cases covering every currently supported
  AST operator, date comparisons, literal string safety and exception priority.
- 37 actual engine evaluations; 16 input/scope guards. The leap-day policy keeps
  M0's explicitly chosen `FEB29_TO_FEB28` convention, not an invented bank rule.
  The 37/8 engine counts in this report refer to gold cases only; fault and
  same-engine recovery calls are additional checks and reported separately.
- Valid zero-match and overlapping UNIQUE tables fail at execution and cannot
  produce a business decision. The initial zero-hit fixture used an empty table
  and failed at deployment; that record is retained and was replaced by a valid
  table with no matching rows to test the intended boundary.
- Malformed XML, missing pinned version and altered compiled payload are rejected.
  Java now independently recomputes the compiled artifact digest before deployment.
- A successful pinned evaluation after these failures proves same-engine
  recovery. It does NOT prove restart/distributed transaction recovery.
- New CI runs the real Java engine and replays retained model-derived IR without
  credentials or model calls. CI completion is reported separately from local runs.

This provides bounded coverage of all operator families, not exhaustive coverage
of their cross-product, maximum integers, arbitrary nesting or concurrent edits.

## 4. Model identity and parameters

The existing employee-agent connection was only read. `/models` returned the
request aliases `deepseek-v4-flash`, `deepseek-v4.1-flash`,
`volcengine/deepseek-v4.1-flash`, `deepseek-v4-pro`; no pinned backend revision was
advertised. No endpoint, model configuration or credentials were changed.

Actual requests fixed `deepseek-v4-flash`, temperature=0.1, top_p=1,
max_tokens=3072, `thinking.type=disabled`, stream=false. The thinking field follows
the [Volcengine Chat API](https://docs.volcengine.com/docs/ark/chat-api?lang=en)
and [DeepSeek thinking-mode protocol](https://api-docs.deepseek.com/guides/thinking_mode/).
All four responses report zero reasoning tokens. This supports that mode mapping
for this batch, not independent proof of sampling-parameter enforcement.

Response model IDs still differ: `deepseek-v4-flash-ga-260731` and
`deepseek-v4-flash-0731`. Their backend equivalence remains **unknown**. The
gateway administrator needs to provide a fixed-version route or a verifiable
alias mapping before comparable model quality experiments. Other probes continue.
Upstream-reported tokens: 10,349 across all four calls, including format failures.
Actual cost remains **unknown**; the gateway billing rate was not provided.

## Reproduction and boundaries

```bash
python3 -m pytest -q
python3 -m probes.flowable.run
python3 -m probes.flowable.run --request evidence/m1-round2/linked-engine-request.json
```

For HTML comparison install `probes/documents/requirements.lock` in an independent
Python 3.11 environment. Generate Docling output via the existing document probe.
Clone RAGFlow at the fixed SHA into ignored `.m1-local/ragflow-src`; install the
official Go 1.27.3 archive under `.m1-local/go` (archive SHA-256
`65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40`).
`python3 -m probes.documents.run_ragflow --source <saved-original.html>` builds
the upstream HTML parser with isolated caches and a bounded Go runtime. Then use
`probes.documents.compare_html --source ... --docling ... --ragflow ...` in that
Python environment. All three inputs must reference the same saved source bytes.

The upstream checkout is untouched except an untracked probe entry point. This
HTML-only no-CGO path deliberately does not run upstream's native-backend build
script; do not extrapolate its results to PDF/Office/DeepDoc. No shared services,
ports, containers, Maven SNAPSHOT installs, Harness workspaces or UI were changed.

## Remaining acceptance gates

1. Deploy and measure an isolated real RAGFlow indexing/retrieval backend, with a
   pinned embedding/reranking configuration; compare a multi-format document set.
2. Process actual policy evidence through extraction, independent semantic gold,
   IR and the real engine; extend scope/category cases beyond these six synthetic
   rules, then validate M2 publication/change failure recovery separately.
3. Resolve model alias mapping and billing evidence; keep every old failure and
   report parser, retrieval, safety and business quality as separate measurements.

PR #1 stays Draft. **No merge, deployment or M1 completion claim.**
