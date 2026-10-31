# H1a history service: frozen contract and isolated handoff

## Contract

Harness ACK: https://github.com/bitlhk/finance-knowledge-factory/pull/6#issuecomment-6535802338

`knowledge-history.v0.1` is now frozen. The historical `.proposed.schema.json`
filename and title remain unchanged to preserve the acknowledged bytes. The
adjacent `knowledge-history-v0.1.freeze.json` records official status.

Schema SHA-256:
`114397ec532e40b84975e5884457ed1de63b45c71a05652c7e8ed5c3f1f3c3c6`.
The old query/session schema, handlers and Core contracts are unchanged.
The proposal report remains historical evidence, not current implementation status.

## Implementation and trust boundary

`m2.history_runtime` verifies independent, private Host history authority and view
lease files. It never issues a lease, modifies a grant, renews a run session,
activates a source or publishes a Manifest. Host files are regular 0600 same-UID
files, with a separate absolute 0700 lease directory. Run-authority schemas and
run-lease schemas are rejected. View leases have at most 15 minutes remaining and
cannot outlive authority. The shared-UID/private-files trust mechanism is isolated
engineering integration, not production SSO or protection against a compromised UID.

The service opens SQLite with `mode=ro` and `query_only=ON`. A read-only subclass
reuses `DocumentCore.replay_document()` without Core initialization DDL or write
transactions. Current product history and source-read rights are mandatory. A
different viewer additionally needs the exact Core receipt history grant and the
Host's exact receipt allow-list. No wildcard/delegation is inferred from a request.

Authorization is checked before disclosure and again after serialization. Immutable
saved receipt, Manifest, historical binding, source revision, index, approval,
validation and anchor content are checked. No current-binding equality is required.
Historical source inactivity is distinct from current source-read revocation.
Revocation committed before the final authorization read is enforced; already
delivered bytes cannot be revoked retroactively.

`savedReceipt` is the exact saved Core object, not an answer archive.
`queryResponse` is its deterministic projection, not regenerated output or claimed
archived HTTP bytes. Host must independently establish the Agent/instance/Lock
association from its own records before issuing access. Factory checks the supplied
original query references, and never changes Harness archives.

Requests are at most 16 KiB. Entire serialized responses are at most 512 KiB;
overflow is a 413 refusal, not partial success. Only acknowledged error names are
returned. Request bodies and bearer credentials are not logged. Eight bounded
HTTP workers use five-second socket timeouts. The standalone process denies all
outbound socket connections/DNS resolution; no model or RAGFlow configuration is
accepted. Termination joins this server's workers only.

## Non-sensitive startup

Run from the fixed Factory worktree, with an **isolated SQLite backup** and a
Host-owned **independent history authority** path. Do not point to a run authority.
Do not pass tokens on the command line. No new Linux service is installed.

```bash
python3 -m m2.history_service \
  --database /home/ubuntu/outputs/knowledge-history-h1a-service/core.sqlite \
  --authority /home/ubuntu/outputs/knowledge-history-h1a-service/host/history-authority.json \
  --product run-39d069d400924257a857cfa7ec64917b \
  --manifest 8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3 \
  --port 61359 \
  --ready-file /home/ubuntu/outputs/knowledge-history-h1a-service/ready.json
```

`--ready-file` and its stopped counterpart must be new files for each launch.
The service may listen before Host provisions its files: this is explicitly
`LISTENING_HOST_AUTH_REQUIRED`, not authorized readiness. All calls then fail
closed with `HISTORY_AUTH_REQUIRED`. Factory does not create Host credentials.

Only `POST http://127.0.0.1:61359/history/read` is exposed. `61358` remains reserved
for Harness and `61353` remains untouched. CLI refuses those ports and a product or
Manifest differing from the fixed H1a binding. Use Ctrl-C in the owning terminal,
or SIGTERM to the exact PID in the readiness record. No shared service is stopped.
After exit, `<ready-name>.stopped.json` records worker completion and outbound
connection attempts. To restart, use a new readiness filename; no query executes
on startup or replay.

## Reproducible acceptance

```bash
python3 -m pytest -q
python3 -m tests.run_history_acceptance \
  --source-database /home/ubuntu/outputs/knowledge-runtime-h1a-705025a/core.sqlite \
  --joint-evidence /home/ubuntu/outputs/knowledge-h1a-closeout/history-joint-01 \
  --output /home/ubuntu/outputs/knowledge-history-acceptance-NEW
```

The acceptance runner creates a backup and temporary **synthetic Host fixtures**,
not authorization for the real Harness UI. It compares the actual stopped Agent's
saved query projection to its archived tool result. It records each HTTP attempt's
full database state before and after, plus process identity and outbound audit.
Only test setup changes policy/binding on the backup. One extra synthetic oversized
receipt is deliberately inserted for the size rejection test; this is NOT counted
as a history-generated query. No original source or historical receipt is rewritten.
The test process is stopped and fixture credentials are removed afterward.

The RAGFlow outage test means upstream configuration is absent and outbound calls
are forbidden. It does not claim or require a shared RAGFlow shutdown. Full UI
acceptance with fresh real Host history authorization remains Harness's task.

## Joint identity

- Agent: `agent-60b8171a34ef479c`
- Instance: `4553dde6-4b96-4828-a934-0c1eb8ea3ce2`
- Core receipt: `6bfafa7dbce44296561fad0b99feea70a7e07f5b6baae012eaa9f4e271ae068e`
- Installation Lock: `2968aec67089c36591986e6ba8ac18e4c59e42ef15f14969f1347d3a3468ef5f`
- Original request: `fh-request-eddedb70-8bff-4870-9821-a637851a2bcf`
- Original trace: `fh-trace-eddedb70-8bff-4870-9821-a637851a2bcf`

These were checked against the saved `history-joint-01/query-events.sse` and
`answer-archive-integrity.json`, not inferred from browser assertions. This does
not independently validate a production identity or a new Harness UI history read.
PR #6 stays Draft, as does the separate Harness integration. No production release,
M2 general acceptance, model-quality acceptance or H1b completion is claimed.
