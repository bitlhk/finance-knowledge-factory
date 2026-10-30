# Web Preview V0.2: real candidate production

## Scope and isolation

This is a single-operator, loopback-only production preview, not a production
release, multi-tenant service, new Knowledge Core, or a Harness installation.
V1.5 remains the product baseline. Its HTML SHA-256 remains
`a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80`.
The initial V0.2 retained the navigation but simplified the original workshop
too far. The V1.5 alignment correction restores its actual layout and interaction
structure; see `WEB-PRODUCTION-V15-ALIGNMENT.md`. The V0.1 evidence viewer is
unchanged and can run on port 61351.
V0.2 runs separately on 61352. No changes to M0, M1 gold, old experiment results,
Harness, Builder, live proxies, or shared Maven artifacts.

This branch is stacked on `feat/web-preview-v01` at `c385a30` (PR #3), which is
itself stacked on M1 (PR #1). Keep the new PR Draft. No merge or production deploy.
Harness H1 remains an independent, blocked assembly task; this UI does not
establish Harness installation, permissions, or end-to-end consumption.

## Real versus unavailable

| Operation | Implementation / boundary |
| --- | --- |
| Import | Local UTF-8 HTML, <=1 MB, explicit numbered clauses; public regulation sample also available |
| Parse / locate | Actual native DOM parsing and M1 anchor verification against original bytes; no external URLs fetched or uploaded scripts executed |
| Document assets | All located clauses, original quotes, source and anchor digests |
| Search | Actual local character-bigram ranking over this run's clauses; NOT RAGFlow, semantic retrieval, or generated FAQ |
| Rule production | New serial DeepSeek calls on 1-2 explicitly selected full clauses, M1 semantic schema and verified lowering; no replay of stored model answers |
| Validation | Structural, source-reference and compilation checks; optional user-supplied retrieval cases; NOT independent business quality acceptance |
| Rule test | Candidate-bound inputs, fixed synthetic Host context, existing guards and actual Flowable 8.0.0 when eligible; no reference-interpreter fallback |
| Full clause | Always review-required; a numeric MET does not authorize a banking operation or approve the whole clause |
| Publishing | No endpoint, no permissions, no M0 Manifest or binding mutation |
| Other capabilities | RAGFlow integration, FAQ compilation, AI-generated test sets, PDF, Word and the other three pipelines are not implemented here |

The current professional recipe is deliberately limited to the existing
personal-loan-duration field vocabulary and templates. Other clauses can be
document knowledge; unsupported rule semantics remain candidates or failures.
The two-clause limit is explicit in recipe selection and output coverage. The
remaining document is not represented as having undergone model extraction.

## Lifecycle and evidence

Each submission pins the source bytes, recipe, selected clauses, test set,
model parameters and implementation file hashes. The UI records new run IDs,
stage timestamps, requests, original model responses, usage, supported lowering,
sidecars, IR, compiled artifacts and errors. Cost remains null, not zero.
Model credentials are never part of these records.

Runs are queued to a single worker, with at most one outstanding production run.
Same request ID and content returns the original run; conflicting content is
rejected, including after restart. There are no model retries. On restart an
unfinished run becomes INTERRUPTED, not silently resumed or reported successful.
Limits: 40 sources and 40 runs in this preview state directory, 2 model calls/run,
30 retrieval cases/run. Model timeout: 180 seconds/call. No source truncation.

A completed run means processing ended, not quality passed. Model failures retain
the document outputs and response evidence and produce PARTIAL. Artifacts are
sealed separately from consumption receipts. Searches and rule tests reference
the run ID and candidate digest; exports include associated receipts. Tampered
candidate content and mismatched receipt bindings are rejected. No production
authorization is implied by these local files. Source authority and full semantic
coverage remain unconfirmed.

The Flowable probe has a separate same-engine recovery check. Receipts now
distinguish primary DMN calls and recovery DMN calls, and sum both as total calls.
The first browser run used an earlier counter that exposed the upstream primary
case count only. Preserve that original export; do not edit it. For its MET case,
the raw report's `recoveryStatus=EXECUTED` proves one additional recovery call.
This is a counting correction, not a changed rule result or score.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
mvn -B -ntp -Dmaven.repo.local="$HOME/.cache/knowledge-production-v02-m2" \
  -f probes/flowable/pom.xml compile dependency:build-classpath \
  -Dmdep.outputFile="$PWD/.m1-local/flowable-classpath.txt"
PATH="$PWD/.venv/bin:$PATH" node web_production/start-managed.cjs \
  /home/ubuntu/outputs/knowledge-web-production-v02/state
```

The launcher reads only the existing, explicitly authorized employee-agent model
catalog over local WebSocket, selecting `deepseek-v4-flash`. It does not modify
that service. Key material passes in child process memory, not CLI arguments,
files, browser responses or logs. The catalog library path can be overridden with
`EMPLOYEE_WS_MODULE`. No account, key, service, or remote ingress is created.

Without that managed connection, run the Python server directly for document-only
testing. Rule production then records MODEL_CONNECTION_UNAVAILABLE rather than
using historical outputs. The standalone server is:

```bash
.venv/bin/python -m web_production.server --port 61352 --state /absolute/isolated/state
```

Open `http://127.0.0.1:61352/` on the development host (or an operator's SSH local
forward). Do not bind to 0.0.0.0 or expose through production Nginx. Host and Origin
checks prevent cross-origin writes but are not multi-user IAM. Local OS users and
the operator's browser are trusted. Runtime files are private to this OS account.
Only import public/authorized content; the recipe requires explicit confirmation
before sending selected material to the managed model.

To stop: read the PID from this state directory's `server.pid`, verify its command
is this `web_production.server` and state directory, then send TERM to that PID.
Do not stop V0.1, the employee-agent service, Harness or any other Codex process.

## Browser walkthrough

1. Knowledge materials: import the public sample, or upload numbered HTML.
2. Production: configure all four steps. Document knowledge is mandatory; rule
   extraction is optional. For the sample, select articles 8 and 43 explicitly.
3. Optionally import a JSON test set, e.g.
   `[{"question":"第四十三条","expectedClause":"第四十三条"}]`.
   These are user checks, not an independent benchmark or model-generated truth.
4. Confirm the model scope; save recipe; click Start Production. Observe real
   processing states, then inspect the new candidate outputs and quality report.
5. Production workshop / candidate validation: open isolated candidate testing,
   search this run's clauses, or submit synthetic facts to a numeric candidate.
   Inspect the guard or actual engine receipt. Formal artifacts and consumption
   stay empty/unavailable because this preview has no formal publication.
6. Refresh or choose an earlier run. Original attempts and candidate digests remain
   unchanged; no model/Provider is invoked merely by reading history.

## Acceptance evidence

The initial browser production on 2026-10-30 imported the public regulation and
made exactly 2 fresh model requests, no retries. Both responses report
`deepseek-v4-flash-ga-260731`, parameters temperature 0.1, top_p 1, max_tokens 4096,
thinking disabled. Total reported usage: 3,142 tokens; monetary cost unknown.

- Run `run-9ef0409f1bea4129903e58342dd4e3e8`: 52 real clause assets, 2 semantic
  candidate groups, 0 extraction failures. This is not a semantic quality pass.
- Article 8: no executable numeric IR was produced. Retained model categorization
  and unsupported conversion decisions are visible; no prompt retry to improve it.
- Article 43: 1 verified short-duration numeric condition; half-duration arithmetic
  remains unsupported; complete-clause decision remains REVIEW_REQUIRED.
- An actual UI rule test returned numeric MET using Flowable. The original receipt
  retains 1 primary call and its separate recovery result (see counting note).
- Uploaded synthetic customer-service HTML: separate run
  `run-f07037e6e9f546d29505fdf9b3aba048`, 2 clauses, no model call, no rule pipeline.
- Refresh, task/source isolation, desktop 1366 and mobile 390/320, no page errors.

The real calls happened before the final commit. Their implementation file hashes
are preserved in the run export; do not claim they used a later commit. Final-build
readback and rule tests are separate and do not re-run model extraction.

Checked-in evidence is in `evidence/web-production-v02/INDEX.json`, including the
unchanged initial exports, both retained-result regression rounds, the final
export and screenshots. The final code-tested commit is `6c32fb9`.
The first retained round exposed a UI discrepancy: input controls reset to
defaults while showing an archived result. This was fixed; final-round tests also
assert that the displayed facts and query match their actual receipts after reload.
No stored attempt or candidate digest changed.

Final local Python regression: **280 passed** (266 baseline + 14 new preview
tests). Final browser regression covers all four pages at 1366/390/320 widths,
unsupported HTML rejection, historical retrieval after server restart, retained
input/result alignment, and zero additional model calls. Four final rule cases:
MET and NOT_MET execute in real Flowable, INVALID_INPUT and NOT_APPLICABLE stop at
guards. That batch has 2 primary DMN calls and 1 recovery call. Across the initial
production smoke and both retained-result rounds, all attempts are preserved:
5 primary DMN calls, 3 recovery calls and 4 guard-only cases. These are technical
checks, not new independent model quality results.

Commands for reproduction (the first makes two new real calls):

```bash
node web_production/check-browser.cjs /absolute/new-evidence-directory
node web_production/check-retained.cjs /absolute/readback-evidence-directory \
  run-9ef0409f1bea4129903e58342dd4e3e8
.venv/bin/python -m pytest -q
```

For the V1.5 layout correction use `node web_production/check-v15.cjs
/absolute/new-evidence-directory`. It uploads synthetic HTML and runs document
production only, with no new model or rule-engine calls. The real-model smoke
script's selectors have been updated, but its model calls were not repeated for
this UI-only correction. Existing model evidence remains historical evidence.

Remaining gates: full semantic quality, RAGFlow service integration and
retrieval-quality benchmark, production IAM/publishing, PDF/Word support and
Harness H1 are not accepted by this preview. No scores or old M1 results changed.
