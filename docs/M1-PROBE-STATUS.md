# M1 component probes: initial evidence, not acceptance

Date: 2026-10-30. Base: `bd725263e4c7d28b14fba9e665d9d180e68e84c8`
(`m0-candidate-v0.1`). Branch: `feat/m1-component-probes`.

M0 Core, contracts, UI, Harness, employee-agent configuration and online services
are unchanged. This branch is an isolated probe candidate, not a production
integration. No candidate was approved or published. License ownership remains
unconfirmed; no license was added.

## Actual results

Sanitized per-attempt records: [initial evidence](../evidence/m1-initial/).

| Probe | Evidence | Boundary |
| --- | --- | --- |
| M0 + probe regression | 140 local tests passed: original 111 plus 29 new tests | Not real-component acceptance; CI matrix adds Python 3.10 and 3.12, CI result separately checked |
| Flowable 8.0.0 | Original 26 gold cases plus two fixed-version cases: 28/28 | 12 actual engine evaluations, 16 input/scope guards; no reference fallback |
| DeepSeek extraction | Eight serial real calls, all completed; eight narrow schema/retention assertions pass | Synthetic data only; extraction envelope, not executable IR; no independent professional acceptance |
| Docling 2.145.0 | Actual public regulation HTML parsed; 36 text items | Body merged into one 5,623-character item, no native provenance; 0/5 distinct clause/location checks pass |
| RAGFlow | Candidate commit identified, not deployed | No retrieval or comparison results; 30 retrieval questions not executed |

Public regulation snapshot: [Ministry of Transport republication](https://credit.mot.gov.cn/zhengcefagui/202408/t20240807_4147084.html).
SHA-256: `d091d80052322f3c933f846dab94078bc7fb25b08565c4fa20530e68e37cb5fa`.
All five checked clause labels exist inside the merged body; the failed check
means *no separate located clause*, not missing text. HTML has no source PDF page
numbers, so none were manufactured. PDF tables, cross-page layout and OCR remain
untested. The XPath matcher is probe adapter code, not Docling-native provenance.

## Findings preserved, not hidden

1. **Compiled identity needed more than the XML hash.** The compiler parameterizes
   literals. Two versions with different thresholds can have identical XML.
   The first two-version run correctly failed duplicate deployment identity.
   The corrected compiled digest includes IR digest, XML, slots, rule identity
   and compiler version. `prepare` rejects stale or changed bindings. In the
   real engine, the same key with different pinned parents returns MET for the
   old 36-month threshold and NOT_MET for the new 12-month threshold on 24 months.
   Initial success, failed expansion log and corrected run remain separate.
2. **Model alias is not yet a stable model-version guarantee.** The selected
   managed connection is `deepseek-v4-flash`, OpenAI-compatible HTTPS through
   the existing Volcengine gateway. Requests fix temperature=0.1, top_p=1 and
   max_tokens=2048. Responses report both `deepseek-v4-flash-ga-260731` and
   `deepseek-v4-flash-0731`. Whether these identify different backends is unknown.
   Do not claim pinned backend consistency from this batch.
3. **Connection metadata is not request evidence.** The employee-agent catalog
   has reasoningLevel=off. This initial standalone client did not propagate that
   provider-specific setting; responses include reasoning tokens. It is not
   evidence that the employee-agent configuration itself is broken. Confirm the
   gateway's supported request mapping before a comparative extraction batch.
4. **Passing narrow safety assertions is not complete extraction quality.** All
   eight outputs request review. C01 and C03 have explicit, supported conditions
   but also request review; C03 treats the synthetic-demo label as uncertainty.
   Over-conservative classification is an open quality issue. Assertions require
   review where necessary but do not score unnecessary review. C06 retains both
   category thresholds, but this envelope does not yet encode their executable
   category-to-condition bindings. Do not send it directly to the compiler.
5. **Parser success is not usable evidence production.** Raw Docling HTML output
   needs source-preserving clause segmentation and a verified locator adapter.
   Do not equate a downstream text offset with an original PDF page or bbox.

## Model access and evidence

The user identified the existing employee-agent model connection. Only the
loopback model catalog was read. Credentials were selected in memory and passed
to one child process, not copied into this repository, prompts or logs. No model
catalog write RPC was called. Credentials remain accessible to the same OS user
and root while the process runs; this does not constitute credential isolation.

Eight requests, no automatic retries, total upstream-reported tokens: 11,002;
sum of request durations: 84.012 seconds. Cost is **unknown**, not zero. The
request alias and returned model names are recorded separately. Recorded
parameters are actual client payload values, not proof of upstream enforcement.
The full public evidence consists only of synthetic messages/results and bounded
component metadata. Local raw evidence remains under ignored `.m1-local/`.

## Reproduction

```bash
python3 -m pytest -q
python3 -m probes.flowable.run
uv venv --python 3.11 .m1-local/docling-venv
uv pip install --python .m1-local/docling-venv/bin/python -r probes/documents/requirements.lock
.m1-local/docling-venv/bin/python -m probes.documents.run_docling
```

The Flowable probe needs Java 21 and Maven. It uses an isolated Maven repository,
in-memory H2 and a bounded JVM; it never installs shared SNAPSHOT artifacts.
Every new run gets its own directory. Model execution is separately opt-in:
`python3 -m probes.llm.run` requires an administrator-supplied HTTPS connection in
the child environment (`OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`). Do not
paste credentials into shell history or commit them. CI does not invoke models.

## M1 gates still open

- Pin or explain backend model identity and explicitly validate reasoning options.
- Real-document extraction into the validated Rule IR with complete scope and
  exception coverage; keep human review and independent gold mandatory.
- Actual RAGFlow deployment and Docling comparison, fixed document suite,
  cross-page/table tests, and 30 independent retrieval questions.
- Full supported-AST differential testing, overlapping/zero-hit DMN behavior and
  artifact corruption/failure recovery. Current 28 cases do not cover all of these.
- Transitive Maven locking and artifact verification. The Docling environment is
  version-locked but not wheel-hash locked; neither is a reproducible supply-chain
  acceptance claim.

**M1 remains in progress. No merge, no deployment, no Harness change.**
