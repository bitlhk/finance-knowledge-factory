# M1 third probe round: real service and source-to-rule evidence

Date: 2026-10-30. Starting commit: `ea708b20543589f0ae061cca48f43e84b807c60d`.
Status: **isolated engineering candidate; PR #1 remains Draft; M1 NOT accepted**.
No main merge, production deployment, V1.5 UI change, M0 kernel/contract change,
Harness change or employee-agent configuration change.

## Results and their scope

| Check | Actual result | What it does not prove |
| --- | --- | --- |
| Python regressions | 182 passed locally, including original M0 coverage | Real-component or business acceptance |
| Real RAGFlow API ingestion | Same HTML bytes; 53 indexed chunks | Native DOM anchors; these still come from the shared adapter |
| Native hybrid retrieval, unchanged 30 questions | 30 completed; top-1 23/30, top-3 28/30 | Reranker quality, full source ACL, or all-document generalization |
| Retrieval source-body verification | Same 23/30 and 28/30 after whole-clause + needle checking | A clause-number mention alone is not counted |
| Negative local access | Independent local account denied (body code 403), anonymous HTTP 401; no additional embedding requests | Core source authorization, production SSO or all denial paths |
| PDF RAGFlow native locations | 52/53 chunks exactly match independent Poppler region text | Complete PDF/table/OCR acceptance |
| PDF Docling native locations | 190/193 text-provenance regions exactly match Poppler | These are different units from RAGFlow chunks; not a parser ranking |
| Word original `.doc` | RAGFlow parsed; clause numbers/usable original locations missing; Docling conversion failed | Word evidence production has NOT passed |
| Real policy, bounded field experiment | 10/10 fixed cases; 5 real Flowable evaluations, 5 guards | Full policy, approval, publication, or stable model quality |
| Existing Flowable regressions | 53/53 (37 engine calls); retained synthetic 14/14 (8 engine calls) | Distributed failure/restart acceptance |

All counters refer to recorded cases; separate fault/recovery invocations are
not added to the gold-case engine counts. CI runs are checked separately from
local probes. [Evidence index](../evidence/m1-round3/INDEX.json) records source run
IDs, original byte hashes, export hashes and any local-path redaction. Earlier
rounds and original failure scores are unchanged.

## 1. Full RAGFlow service, not an internal-package substitute

Official `v1.0.0-rc2` image pinned to
`sha256:141670c7d25b4421f6378152e583a0fe7e5280ed750c42f7507759192d0dad82`.
This round actually ran API, admin, ingestor, MySQL, Elasticsearch, NATS, KVrocks
and MinIO-compatible storage in the independent `kf-m1-ragflow` Docker project.
HTTP APIs performed registration, embedding configuration, upload, parsing,
chunk listing and retrieval. No RAGFlow parser source was substituted.

Embedding: actual local CPU FastEmbed 0.7.3, `BAAI/bge-small-zh-v1.5`, 512 dimensions.
ONNX/tokenizer file hashes and container image digests are retained. No mock vectors
or external paid embedding calls. Search parameters: keyword weight 0.7, kNN 64,
candidate count 128, page size 3, no reranker, no LLM compilation. Dataset `laws`
parser configuration is retained. This is a real **hybrid baseline**, not the old
shared BM25 diagnostic and not proof of RAGFlow's best achievable quality.

Old top-3 failures Q01/Q08/Q21/Q25 remain in the fixed test set. Q08 is now top-1;
Q21 appears in top-3; Q01 and Q25 still fail. The new ranking uses a different
indexing/embedding process; no causal claim that Knowledge Core improved ranking.
The source verification requires full original clause content and the frozen
needle, preventing cross-reference-only false hits.

The other probe user is an independently registered RAGFlow account, not a forged
identity header. Denied requests returned no data and embedding counts remained
unchanged (35/35 in the first check). Upstream access checks precede embedding and
search (`internal/service/dataset/search.go` in pinned source). This does not
implement or validate Knowledge Core's per-source ACL, consume/history split,
revocation propagation or real customer account isolation.

Operational evidence: loopback API/admin ports 19380/19381, a password-protected
embedding adapter bound only to the private Docker bridge, memory/CPU limits,
no privileged container or host Docker socket mount, no public endpoint. Random
local credentials were stored in ignored 0600 files. **Upstream bootstrap admin
uses its built-in default, not our random storage password**; this stack must not
be exposed or reused as production. All eight containers and the embedding
listener were stopped at the end; data volumes retained. See the stop receipt.

## 2. Cross-format results without invented locations

HTML uses the prior official Ministry of Transport snapshot, byte-identical to
round 2. A minimal [native evidence sidecar](EVIDENCE-ANCHOR-PROBE.md) bridges its
101 verified DOM anchors and 52 clauses to legacy M0 derived-line references.
Rule predicates, applicability exceptions and unresolved references all retain
their original anchors. The sidecar is probe-only, not a new M0 release feature.

Word: downloaded the actual 64,000-byte OLE `.doc` attachment from the
[Jining government page](https://jkq.jining.gov.cn/art/2024/2/27/art_71912_2722624.html).
It was not renamed to DOCX. RAGFlow ingestion succeeds, but indexed text loses
the original clause numbering and supplies no usable original locations.
Docling first lacked its optional Word dependency; after installing it in an
isolated venv, conversion still failed. The hardened LibreOffice diagnostic
returns exit 0 with `source file could not be loaded` and produces no DOCX.
Host inventory has core/draw/impress but no installed Writer package. Missing
Writer is a concrete environment gap; a full Writer image has not been tested.
The host's office installation was not changed. No converted document is claimed.

PDF: downloaded a [secondary publisher copy](https://n1.sinaimg.cn/www/c24b74a7/20240202/3.pdf)
of the same titled regulation. Its receipt explicitly says SECONDARY_REPRODUCTION,
not an authority activation. It has 14 real pages. The Word and PDF cover metadata
also differ (January 30 versus February 2): identical legal text/version across
these copies is **not assumed** or certified.

Both parsers actually processed those same PDF bytes. RAGFlow produced 53 chunks
with page rectangles; independent `pdftotext 24.02.0 -bbox` verifies 52 exactly
after NFKC/whitespace normalization. The final chunk combines clause 52 and an
appendix; its cross-page header/text mismatch remains a failure.

Docling initially failed for missing PDF extras, then a missing `packaging`
dependency. We retained both records, installed the pinned standard dependencies
in its own venv with **CPU-only** Torch, and retried with OCR/table extraction off
and two CPU threads. Actual output: 193 text items with page provenance, 190 exact
matches. Three mismatches involve page-footer text and a merged cross-page clause
fragment (`#/texts/28`, `#/texts/82`, `#/texts/137`). Table/scanned-PDF acceptance is
not claimed. Model weights stay in the private probe cache; no global packages.

The location checks test source coordinates, not merely the existence of a page
field. They do not yet make PDF/Word references consumable through the HTML-only
M0 sidecar bridge. No claim that the entire cross-format gate is closed.

## 3. Real policy extraction: all five calls and failures retained

Three full-clause inputs (43, 8, 33) were frozen with bounded subcondition gold
before any call. They use the real source text, trusted POC field names and scope.
They are engineer-authored technical gold, **not independent business-owner or
blind acceptance**, and never authorize loan/extension/payment decisions.

| Attempt | Result | Diagnosis |
| --- | --- | --- |
| P43 full clause | 4/10 gold checks; correct numeric predicate but excessive review | Model retained the explicitly excluded >1-year branch as unresolved, suppressing in-scope evaluation |
| P08 full clause | 12/12 review decisions, overall extraction assessment fails | Returned 3 rules rather than frozen 2; cash-flow eligibility was not properly bound to the extended-term rule |
| P33 full clause | 2/2 review decisions and retention checks | Missing clause 36 remains unresolved, not invented |
| P43-NARROW, separately frozen original subspan | 5/10 | Applicability used unrelated `months` instead of `original_months`; UNKNOWN is retained, not changed to MET |
| P43-BOUND-FIELDS, new request | 10/10 | Exposed only original term and cumulative extension with explicit meanings; real Flowable 5 calls + 5 guards |

P08's exact rule-count criterion is a representation constraint, not by itself
proof of semantic error: three rules could be a valid decomposition. The separate
semantic concern is that its extended branch uses BUSINESS and months>60 without
a verified cash-flow eligibility condition. Existing unresolved external provisions
keep it at REVIEW_REQUIRED, so there was no unsafe MET in these recorded cases.
The original assessment remains unchanged; no format/rubric adjustment hides it.

The bounded-fields experiment does not repair an old answer or broaden accepted
inputs. Its original subspan and gold values are retained, with a new request
digest and a restricted field registry. It demonstrates a **single numeric
subcondition** from original HTML through evidence binding, model extraction,
validated IR, compiled-identity check and real Flowable. Other policy provisions,
consent, risk review, exemptions, complete applicability and authority activation
are explicitly unverified. No rule or candidate is published.

All five real requests completed. Strict JSON: **1/5**; four returned one complete
JSON fence and were processed by the existing bounded decoder, with raw output
and format status preserved. Upstream-reported tokens: **14,038** including failed
attempts; cost **unknown**. Request alias `deepseek-v4-flash`, temperature 0.1,
top_p 1, max_tokens 4096, thinking disabled. Two returned backend identifiers
remain; equivalence and sampling enforcement are unknown. These are diagnostic
attempts, not a controlled model-quality comparison.

An engineering defect was also exposed: the Java probe assumed at least one
unguarded MET case for its recovery check, then threw `NoSuchElementException`
before saving an all-guarded run. The minimal fix saves the complete report and
marks recovery **NOT_EXECUTED_NO_ELIGIBLE_CASE**, not success. Replaying the same
retained input preserves 18/24 gold passes, 6 failures, and zero engine evaluations.
The initial error log is kept. CI explicitly checks this expected failure behavior.

## 4. What remains before M1 acceptance

1. Word native or explicitly traceable conversion evidence; resolve PDF region
   mismatches; freeze a broader cross-format set including tables. Do not select
   a universal parser from this single policy. Core-level authorization still
   needs the real service adapter; local RAGFlow ACL alone is insufficient.
2. Complete semantic validation of real conditions, scope, exceptions and external
   references. The bounded numeric success does not close P08/P43 full-clause
   failures. Separate reviewer gold from representation preferences, preserve all
   outcomes, and obtain a fixed or verifiably mapped model route for quality tests.

M2's trusted source activation, atomic artifact closure/release and failure
recovery remain separate. M3's Knowledge Provider/Lock integration remains
separate. UI, navigation and other three production lines are not expanded.

## Reproduction

```bash
python3 -m pytest -q
python3 -m probes.flowable.run
python3 -m probes.flowable.run --request evidence/m1-round2/linked-engine-request.json
python3 -m probes.flowable.run --request evidence/m1-round3/policy/bounded-fields/engine-request.json
python3 -m probes.flowable.replay_guarded
```

These commands need no model credentials. Real RAGFlow preparation and service
probes are in [the isolated service guide](M1-RAGFLOW-SERVICE.md). Model calls are
opt-in via `probes.llm.run_policy`; each invocation creates a separate evidence
directory and has no automatic retries. Never put API keys in CLI arguments,
repository files or published evidence. The existing managed model connection
was read only, passed in memory to a child, and not reconfigured.
