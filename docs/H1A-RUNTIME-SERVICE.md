# H1a isolated Runtime service

This delivery is Factory consumption wiring only. It does not close H1a or M2.
V1.5 preview 61353, M0 business code, original database, grants, activation records,
Harness/Builder and historical evidence are not modified. PR 6 remains Draft.

## Start for joint testing

Run from this worktree with its existing Python dependencies. The Host team must
first provide a private authority policy and issue the session using its existing
authority implementation. Do not pass bearer credentials on the command line.

Create a fresh private directory and a SQLite backup of the original fixed product
using Python's sqlite3 backup API with the source opened `mode=ro`. This is a data
copy only; no approval, grant or source activation is added. Do not reuse the
acceptance-test database, which deliberately ends with a revoked source. The
joint test database is a separate isolated authority state, not a replica that
automatically receives later permission changes in the preview database.

After the Host team confirms the policy file path and the isolated database path:

```bash
cd /home/ubuntu/worktrees/knowledge-factory-m2-web
python3 -m m2.runtime_service \
  --database "$H1A_CORE_DATABASE" \
  --authority "$H1A_HOST_AUTHORITY" \
  --private-config /home/ubuntu/worktrees/knowledge-factory-m1-probes/.m1-local/ragflow-service \
  --port 61357 \
  --ready-file "$H1A_RUN_DIRECTORY/runtime-ready.json"
```

The three H1A variables are server filesystem paths, not secrets. The readiness
file must not already exist. The server listens only on 127.0.0.1. Existing
`python3 -m m2.host_leases` arguments are left unchanged for compatibility, but the
new pinned/limited service entrypoint above is the joint-test candidate.

Stop with Ctrl-C in that terminal, or `kill -TERM <pid-from-this-ready-file>` after
checking that it belongs to this invocation. Do not use pkill or stop shared
services. SIGTERM/INT closes only this HTTP listener, waits for its workers and
writes a private `runtime-ready.stopped.json`. It never shuts down RAGFlow, preview,
Harness or Builder. Readiness means listening, not that a Host identity is accepted;
authenticated POST /session is the consumption health check. No public health API.

## Repeat Factory acceptance

```bash
python3 -m m2.runtime_acceptance \
  --database /home/ubuntu/outputs/knowledge-m2-web/app/core.sqlite \
  --private-config /home/ubuntu/worktrees/knowledge-factory-m1-probes/.m1-local/ragflow-service \
  --output /home/ubuntu/outputs/knowledge-runtime-http-NEW-RUN \
  --port 61357
python3 -m pytest tests/test_runtime_http.py tests/test_harness_runtime.py tests/test_host_leases.py -q
```

The output directory must be new. Acceptance creates a read-only-source SQLite
backup and synthetic Host fixture files in that directory, starts an actual child
server, uses real RAGFlow retrieval, terminates/restarts only its own server, then
removes fixture authority/lease files. The bearer exists only in process memory.
The test fixture writer is not part of the deployed Runtime or a Host replacement.
Generative model calls are zero; embedding/accounting cost remains unknown.

Controlled HTTP tests use a separate local upstream, exercising RAGFlow's actual
HTTP parser for HTTP-200 business denial, HTTP-503, invalid JSON, dataset/document
mismatch and corrupted text. Recovery is the next request to that controlled
upstream. No failure is injected into the shared live RAGFlow service. Additional
barrier tests revoke lease/source/product/binding during retrieval and after final
session resolution, checking that no evidence is disclosed.

## Evidence discipline

Reports retain every attempt, actual process code identity and module/schema
digests. Dirty-tree executions are not relabelled as committed-code runs. Original
database governance and full logical object/history hashes are compared before
and after; new query receipts exist only in the copied database. Old reports and
scores are never rewritten.

The first script attempt stopped at ACTIVATION_ORDER_CONFLICT after 25 successful
HTTP checks because it tried to append a source event on the already-used date.
The correction advances only the test fixture's trusted date and appends a later
event on the copied database. This does not relax Core's immutable activation rule.
Early controlled tests also corrected a future-date fixture and a mistaken test
helper name; neither required changing Core. Results from corrected scripts are
reported separately.

See [the shared wire handoff](../contracts/runtime/README.md) for the exact fixed
product, Manifest, protocols, error handling and remaining joint-test obligations.
There is no Installation Lock or Agent-page acceptance in this Factory delivery.
