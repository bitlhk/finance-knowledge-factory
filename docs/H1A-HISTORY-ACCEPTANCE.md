# Factory H1a history read: implementation acceptance

Status: **FACTORY ISOLATED HTTP ACCEPTED; HARNESS SAME-INSTANCE UI JOINT ACCEPTANCE PENDING**.
No production identity, model quality, general M2 or H1b acceptance is claimed.

Executed clean code: `e4b45e4ad6796253f07a8d7feb8e878162a469fa`.
Base: `7c6b0988d62448b195725734607b513637721a7b`.
Evidence: `evidence/h1a-history/`; original local run:
`/home/ubuntu/outputs/knowledge-history-h1a-e4b45e4/`.
The evidence/docs commit does not replace the recorded execution SHA.

## Results

| Check | Observed result |
| --- | --- |
| Full local regression on fixed code | 434 passed, 0 failed, 0 skipped; 44.14 seconds |
| New focused history tests | 45 passed |
| Actual saved receipt over standalone HTTP | 16/16 scenarios passed |
| Normal read and repeated read | Original saved object and Harness tool-result projection equal |
| Missing/forged/wrong-type/expired authority | 403, no evidence |
| Source-read and product-history revocation | 403, no evidence |
| Cross-principal without exact receipt grant | 403 |
| Cross-principal with exact Host AND Core grants | 200; original evidence and principal preserved |
| Exact receipt grant removed | 403 |
| Original Manifest assertion mismatch | 409 HISTORY_REFERENCE_MISMATCH |
| Entire oversized response | 413 HISTORY_RESPONSE_LIMIT, no truncated success |
| Original Manifest no longer current | Authorized historical read succeeds |
| Source inactive for future consumption | Historical read succeeds; source-read revocation still fails |
| Per-read database mutation | Zero: full objects/heads/identities/activations snapshot equal before/after every HTTP attempt |
| Outbound socket attempts | Zero; outbound connection/DNS guard enabled in standalone process |
| RAGFlow / model invocations | 0 / 0; no upstream configuration, no retrieval or model operation |
| History-generated query receipts | 0 |
| Source database state / receipt inventory | Identical before and after; original receipt count remains 18 |

Unit/HTTP regression additionally covers all six original reference assertions,
corrupt index/anchor/receipt data, absent storage and recovery, permissions revoked
during response construction, strict JSON/framing, authority file permissions,
symlinks, read-only SQL writes and forbidden query/session/publication routes.

The HTTP test runner changes **only its backup** to exercise grants/revocation and
inactive bindings. It inserts one additional synthetic oversized saved receipt for
the response-limit case. Thus test-copy final receipt count is 19, not 18; this is
explicit setup, not a history API side effect. No count has been hidden or relabeled.
The inactive-source fixture is checked at business date 2099-01-02. History itself
does not invent a current business date or re-run applicability.

RAGFlow unavailability is tested by running a history-only process with no upstream
configuration and an enforced deny-all outbound hook. The shared RAGFlow service
was not stopped. Controlled Host fixtures are temporary and removed after the run;
they do not constitute real Harness viewer authorization.

## Preserved execution identities and failures

The two earlier development executions are retained at
`/home/ubuntu/outputs/knowledge-history-h1a-development-01/` and
`/home/ubuntu/outputs/knowledge-history-h1a-development-02/`.
They explicitly record the old HEAD with `dirty=true`, not a false clean SHA.
Both HTTP runs passed 16 cases. The first full JUnit run passed 434 tests with 12
existing xunit2/record_property format warnings. The fixed-code run used xunit1
and passed 434 without those warnings. No failing test was deleted or re-scored;
refusals and their full HTTP bodies are retained beside successful reads.

Fixed-code GitHub checks also passed:
- Python 3.10 / 3.12: https://github.com/bitlhk/finance-knowledge-factory/actions/runs/41146951847
- Real Flowable regression: https://github.com/bitlhk/finance-knowledge-factory/actions/runs/41146951920

These do not rerun external LLM extraction or establish new rule-quality scores.

## Frozen protocol and running handoff

Schema SHA-256:
`114397ec532e40b84975e5884457ed1de63b45c71a05652c7e8ed5c3f1f3c3c6`.
Query/session schema is unchanged:
`ae9fa3dbf053829144983f3d23892eeef93d43e1a755f0306ccd0a01a209c4fa`.

Handoff listener: `http://127.0.0.1:61359/history/read`.
Readiness: `/home/ubuntu/outputs/knowledge-history-h1a-service/ready.json`.
Current process PID at handoff: `1792456`, code `e4b45e4`, clean start.
It uses a separate **unmodified fresh backup**, NOT the mutated acceptance backup.
Startup and stop instructions: [H1A-HISTORY-SERVICE.md](H1A-HISTORY-SERVICE.md).

No Host authority file was created by Factory. Harness must provide the independent
history policy at
`/home/ubuntu/outputs/knowledge-history-h1a-service/host/history-authority.json`
and its separately protected history lease directory. Without this, endpoint
returns `403 HISTORY_AUTH_REQUIRED`; verified on the running listener. Listening
does not mean authorized joint acceptance. Factory has not renewed or reused any
stopped Agent run lease, and does not modify the Host's answer archive.

Harness handoff:
https://github.com/bitlhk/finance-agent-harness/pull/96#issuecomment-6536027489

## Remaining gate

Harness must issue real local-workbench history authorization for the saved
`agent-60b8171a34ef479c` instance `4553dde6-4b96-4828-a934-0c1eb8ea3ce2`, enforce
its own viewer/record/Installation Lock relationship and return the same-instance
stopped-Agent UI read evidence. Factory's synthetic Host tests cannot replace it.

The original archived tool result and archive-integrity metadata correlate the
fixed Manifest, receipt and Lock. `stopped.json` also identifies this build and
instance as `STOPPED`. Those files were read, not rewritten. Core does not contain
the Agent answer archive and this endpoint does not generate one.

61353 has not been restarted (existing PID 90035), 61358 remains reserved for
Harness, original M2 sources/rights/activations/receipts remain untouched. Neither
Harness nor Builder code was edited. PR #6 stays Draft; no merge or production
deployment was performed.
