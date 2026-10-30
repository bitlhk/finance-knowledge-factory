# Isolated Wiki compilation probe

Date: 2026-10-30. Base: `8c56cb3`. Branch: `feat/m1-wiki-worker-probe`.
Separate from PR #1. No Core, UI, Harness, upstream repository, service,
permission or publication changes. No public listener.

## Provenance and actual reuse

Upstream: https://gitcode.com/wangkun_123/Knowledge_builder.git
Pinned commit: `cbbc609e5b8155a29c511b21ce412097e4c2e07a`.
The isolated clone is only read. The loader verifies HEAD **and actual bytes** of
the four imported files against that commit. It calls upstream
`get_build_profile('generic')` and `build_topic_user_message`, and uses its
`topic_prompt`. It does not copy or run their publishing/Agent/permission systems.

This is **a single-page compilation function probe**, not acceptance of their
entire `build_wiki` pipeline or its OpenJiuwen transport. Our small transport
adapter uses the authorized existing Volcengine DeepSeek HTTPS connection.
Upstream root license is MIT (copyright 2026 wangkun_123); its `knowledgebuilder/`
subtree has a separate Apache license. No upstream source was vendored here.
Any future vendoring must preserve the applicable license and provenance.

## Input and output

Four frozen synthetic customer-service facts, one topic, explicit line anchors.
No bank customer data. Model receives source and upstream prompt plus an explicit
source-anchor convention. Source budget exceeded => reject before invocation;
incomplete output => no complete-coverage claim. No retries.

Real call: `deepseek-v4-flash`, temperature 0.1, top_p 1, max_tokens 2048,
thinking disabled. Response model `deepseek-v4-flash-ga-260731`, 796 reported
tokens, 4,039 ms. Cost unknown. Key stayed in process memory, not artifacts.

Output has a title, body, reference list, source/recipe/request/response digests,
model identifier and candidate status. No related page exists, so topicRelations
is empty, not fabricated. Four native line anchors are retained; no fake PDF pages.

## Results and limitations

- Real model call completed. Initial structure/source-anchor gate passed 4/4
  expected anchor IDs. This only establishes reference existence and coverage.
- Downstream handoff gate **BLOCKED** the candidate: generated
  `[[raw/客服资料补正说明]]` points to no delivered page, and an unmatched trailing
  code fence remains. Original candidate, original structural result and raw
  response are retained; `handoff.json` is an additional assessment, not a rewrite.
- Generated wording includes "避免客户多次往返", which is plausible extra help
  but not explicitly in the source. Semantic entailment remains REVIEW_REQUIRED;
  a source tag alone does not prove every sentence is supported.
- Local regression: **193 passed**, including 11 probe-specific cases and the
  original 182 baseline tests. This is not full upstream application acceptance.

Upstream integration hazards found by source review:
`pipeline.py` generic topic generation receives `_truncated` but does not reject
it; skipped model failures do not increment the `failed` save counter, so the
final trace can say success despite fewer saved pages. A production adapter must
independently check source coverage, completed pages and final response status.
We did not modify the coworker's implementation.

## Reproduce

```bash
python3 -m pytest -q tests/test_wiki_worker_probe.py
python3 -m probes.wiki.worker_probe --upstream /path/to/pinned/Knowledge_builder --output NEW_DIRECTORY
python3 -m probes.wiki.handoff NEW_DIRECTORY
```

The actual model command requires OPENAI_BASE_URL, OPENAI_API_KEY and OPENAI_MODEL
in process environment, with the existing managed DeepSeek connection. Never put
the key in CLI arguments. The probe imports only reviewed upstream profile modules
in a dedicated process; it does not install the full upstream application.

## Next boundary

Before M2 admission, agree a worker result contract with the coworker: exported
page manifest, source-anchor references, complete/partial/failed state, truncation
and model request metadata. Resolve actual page links instead of inventing source
files to satisfy the UI. Candidate validation/publication remain in Knowledge
Core. This probe must not block or inflate PR #1's rule-semantic acceptance.
