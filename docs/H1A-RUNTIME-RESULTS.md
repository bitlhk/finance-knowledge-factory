# Factory Runtime HTTP acceptance, 2026-10-30

Status: **Factory isolated Runtime candidate passed; joint H1a NOT accepted**.
PR 6 remains Draft. No merge or production deployment.

## Executed code and fixed data

- Server code: `705025a8de130446897971bdf388d3b47b5252ca`, clean worktree.
- Starting baseline: `2c40495a223f8cd1ec4f85aff3168d9e4491bc8e`.
- Protocol schema SHA-256:
  `ae9fa3dbf053829144983f3d23892eeef93d43e1a755f0306ccd0a01a209c4fa`.
- Product: `run-39d069d400924257a857cfa7ec64917b`.
- Manifest: `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
- Producer and unchanged preview 61353: `c2939742f211a1ed363dc792d3602d0098765a04`.
- Harness contract inspected at `3dacab04e2a4a4f58baa48177c0cdf5a31a5415d`.
  Inspection is not an installed Java Agent test or the other team's acceptance.

The subsequent evidence/documentation commit does not change executable files.
Readiness records retain the actual executed commit and module hashes, not a
retrospectively substituted final PR head.

## Results

| Layer | Result | What it proves |
| --- | --- | --- |
| Actual standalone HTTP process | 35/35 checks | Existing session/query protocol, fixed snapshot and private lease boundary |
| Real RAGFlow retrieval | 4/4 responses, three fixed questions plus one post-restart repeat | Returned original evidence and saved Core receipts; not general retrieval-quality acceptance |
| Denials in standalone run | 26/26 expected refusals | Missing/wrong/expired/revoked leases, context/purpose/subject/Manifest mismatch, missing trusted context, current source/product permissions and source invalidation |
| Process recovery | Same port, new PID, same copied DB and Manifest | Session/query work after restart; old receipt is readable without rerunning it |
| Controlled HTTP and lease/runtime regression | 48/48 within full suite | Includes 18 new tests; actual sockets with controlled upstream failures and in-flight revocation |
| Full Python regression | 374 passed, 0 failed/skipped | Existing 356 plus 18 new tests; no generative-model quality claim |
| Original database | Governance and all logical objects/history unchanged | Source opened read-only for backup; mutations and new receipts only in test copy |
| Stop | Both own process invocations exited 0; workers joined | Only the Runtime HTTP process, not Agent or all OS resources |

The controlled fault cases include upstream HTTP 200 with business code 403,
HTTP 503, malformed JSON, wrong dataset/document and changed source text. Each
refused response contained no evidence or success receipt; a following healthy
request succeeded. These are fault-injected local HTTP upstreams using the real
RAGFlow response parser, not an outage/restart of the shared live RAGFlow service.

In-flight tests cover expired/revoked lease, source/product permission revocation,
source invalidation, changed current Manifest binding, and Core revocation during
the final Host session resolution. The final response is refused. Internal receipt
existence alone is not counted as successful user disclosure.

## Preserved attempts and files

- `knowledge-runtime-http-r1`: failed after 25 passing HTTP checks on a same-date
  test activation; error `ACTIVATION_ORDER_CONFLICT`, preserved. It used an earlier
  dirty candidate and is not attributed to 705025a.
- `knowledge-runtime-http-r2`: 32/32 after correcting fixture activation/restart.
- `knowledge-runtime-http-r3`: 32/32 after schema/record refinements; local evidence
  retained. Both are pre-commit intermediate runs, not final execution evidence.
- `knowledge-runtime-http-r4`: final 35/35, both server invocations identify clean
  705025a. Full 374-test regression also executed at this commit.

Local attempts: `/home/ubuntu/outputs/knowledge-runtime-http-r{1,2,3,4}/`.
Selected credential-free evidence is archived in
[`evidence/h1a-runtime-http`](../evidence/h1a-runtime-http/): original failed report,
committed successful HTTP report (including denial bodies and Core receipts),
full JUnit XML with controlled transport evidence, preview version comparison and
file digests. Test SQLite databases and private configuration are not published.
Fixture authority/lease files were removed; their bearer was never saved.

Generative model calls: 0. Retrieval may use existing embedding infrastructure;
no billing evidence was collected, so cost remains unknown, not zero.

## Ready for the other development line

A fresh, unmodified governance copy for joint testing is prepared at
`/home/ubuntu/outputs/knowledge-runtime-h1a-705025a/core.sqlite` (private directory,
file mode 0600). It is NOT the revoked negative-test copy. No Host identity or
lease has been created for it, and no Runtime is currently listening on 61357.

After Harness supplies its private policy path, start from the Factory worktree:

```bash
python3 -m m2.runtime_service \
  --database /home/ubuntu/outputs/knowledge-runtime-h1a-705025a/core.sqlite \
  --authority "$H1A_HOST_AUTHORITY" \
  --private-config /home/ubuntu/worktrees/knowledge-factory-m1-probes/.m1-local/ragflow-service \
  --port 61357 \
  --ready-file /home/ubuntu/outputs/knowledge-runtime-h1a-705025a/runtime-ready.json
```

`H1A_HOST_AUTHORITY` is the Host team's existing private policy file path, not a
bearer/key. The policy/lease must match this product/Manifest and the current Core
permissions. No tool/browser may supply identity, date, endpoint or new grants.
Use Ctrl-C or SIGTERM to this exact PID to stop. See
[the startup guide](H1A-RUNTIME-SERVICE.md) and
[the protocol handoff](../contracts/runtime/README.md).

## Explicitly incomplete

1. Joint acknowledgement of the frozen interface and paired Harness/Builder SHAs.
2. Actual Host-issued lease through a Builder-installed Agent; qualification,
   Installation Lock, existing Agent-page query, stop and history on one instance.
3. Production IAM, live preview-policy replication, H1b, full OS cleanup and M1
   business-rule semantic acceptance. None is implied by this service result.

Factory checks the isolated copy's current permissions. Changes to preview 61353
are not synchronized into that copy. Joint revocation tests must target the copy's
current Core state, never mutate the preserved preview to manufacture evidence.
