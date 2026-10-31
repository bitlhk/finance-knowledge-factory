# Document index readiness, 2026-10-31

First failure retained: `run-1a00ac5f19f64e42bf4afa777c47acbc`,
`RAGFLOW_CHUNKS_INCOMPLETE`, at 07:49:09.835062 UTC. HTML parsing had
identified 52 clauses. Retrieval tests had not started. No candidate was created.

The adapter previously read one chunk page once immediately after parse progress
reached 1. The same saved RAGFlow document subsequently returned all 53 chunks.
The original response counts were not recorded, so delayed index visibility is
the leading explanation, not a proven reconstruction of the failing response.
The 52 numbered clauses and 53 RAGFlow chunks are different units.

The fix polls only chunk reads, for at most 30 seconds between bounded HTTP
requests, and requires two consecutive complete, identical ID/text snapshots.
It follows pages of 100 up to an explicit 1,000-chunk limit. Malformed data,
duplicate IDs and over-limit results fail closed. Incomplete indexes still fail;
no ingestion retry, auth retry, model call or relaxed Core check is introduced.
Each snapshot check records expected/received counts and stability in the job's
native operations, including on failure. HTTP requests retain their own timeout.

Verification: 51 tests passed across chunk visibility, HTTP envelopes, document
Core and M2 web integration. These are controlled tests, not production success.
Real read-only verification of the failed run's existing dataset/document returned
53 unique chunks, twice with identical content. No ingestion, retrieval, model
call, approval or publication was performed. A fresh full production run remains
to be verified by the user; old failure records are not rewritten.

Evidence: `/home/ubuntu/outputs/knowledge-loan-index-20261031/` contains the
original run response and the actual read-only check report. The initial evidence
script invocation lacked PYTHONPATH and exited before any network operation;
rerunning with the project import path completed the read-only check.

Scope: the Zhishi development service only; no changes to Harness, production
Shanghai services, original M2 data, permissions or publication policies.
