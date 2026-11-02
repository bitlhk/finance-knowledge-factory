# PR #14 AMSYLJ01 isolated acceptance

## Decision

The first real Bank of China business product is structurally reproducible and
can run through the isolated PR #13 Core, Worker, and Gateway services, but its
current quality result is **REJECT**. No Manifest was created. This result is
retained rather than changing the frozen questions, prompt, retrieval profile,
or quality thresholds.

## Fixed sources and conversion

The controlled adapter accepts exactly three registered official byte streams:

| Source | SHA-256 | Processing |
| --- | --- | --- |
| AMSYLJ01 product specification PDF | `ffd336f6eb5544900c700fa87f76511e7661563f705a1947ceb68a5999e7109e` | Poppler 24.02.0, 9 physical pages |
| BOC self-managed wealth agreement HTML | `60dc1e97e6ec744b9e804316c9ccc0026b9caedf20a9ba6a62b00d58e9c989dd` | verified DOM text node |
| BOC investor-rights HTML | `96682c229889c377316cadb827f9a10d42e112f5c9e351f0ffdf80581d3562d7` | verified DOM text node |

The conversion produced 24 evidence units. Every derived HTML quote maps to a
PDF physical page or a normalized official-HTML XPath and quote digest. The
provenance digest is
`8b194b5566a928f455bf1b174d09651b9c25f4a2846ed8fd511d9076cc4c97dd`.
Digest damage, page-marker loss, incomplete index mapping, or anchor mismatch
fails closed. This is a product-specific adapter, not generic PDF support.

## Real isolated execution

- Candidate: `6f991c252d59c2776ca61c3ea005b9a600f76555711ee5d328a067b9770fb2b6`
- Source: `5cecd1b01743ae4ecd5df9a84f4d4ad8e00d1ba0a4ec898c9445c4c0d84a2a3d`
- Index: `d98087008cdab541851d9cbbffc99650aa1f5e8de966758621b671e1049d3b2d`
- Assignment: `253f6396ba03a92019a6f9bd6e8c0ba87866add1a445d7fcca2afbb2f5d8e655`
- Runtime evidence: `a16f0eb12126c2476760f40c817665ed8ed671f4c94e2e3d3fa16036872f56c4`
- Answer evaluation: `58991a0d902b4a990f8c6522a384441d9b779d5227c8c94ffd06bf7681dbccbb`
- Quality admission: `0279e0e70bf6429ca8a79bd88a9efc97a7babbbab5cf128a17f7f2803ae8766c`
- Model: Volcengine `deepseek-v4-flash`, OpenJiuwen `0.1.17.post1`
- Verification: `CORE_CORRELATED_FACTORY_WORKER`

The Worker made 18 real model calls through the isolated Gateway. Core
correlated all candidate and model receipts and independently returned REJECT.
RAGFlow retrieval measured Hit@1 6875 bps, Recall@3 3750 bps, MRR 7708 bps,
and no-answer false-positive 5000 bps. Answer checks measured fact accuracy 769
bps, citation accuracy 5172 bps, and forbidden-claim accuracy 10000 bps.

## Per-case outcome

| Case | Result | Main observed reason |
| --- | --- | --- |
| wm-001 | fail | product risk-level evidence was not retrieved |
| wm-002 | fail | product evidence missing; correctly withheld suitability decision |
| wm-003 | fail | answer was materially correct; lexical fact checks did not accept paraphrases |
| wm-004 | fail | normal redemption evidence missing; answer confused redemption with product termination |
| wm-005 | fail | answer was materially correct; second required evidence and lexical facts failed |
| wm-006 | fail | amount answer was correct; one required citation and lexical facts failed |
| wm-007 | fail | answer was materially correct; lexical facts failed |
| wm-008 | fail | main fees answered; complete multi-evidence support and tax caveat missing |
| wm-009 | fail | non-guarantee conclusion correct; full evidence/fact support incomplete |
| wm-010 | fail | prohibition correct; self-funds evidence and lexical facts incomplete |
| wm-011 | fail | distinction recognized but normal-redemption evidence was missing |
| wm-012 | fail | answer was materially correct; lexical facts failed |
| wm-013 | fail | answer was materially correct; lexical facts failed |
| wm-014 | fail | precedence answer was materially correct; lexical fact failed |
| wm-015 | pass | correctly refused to assert current sale status or quota |
| wm-016 | fail | correctly requested live customer checks; product evidence/fact checks incomplete |
| wm-017 | fail | correctly refused a current yield assertion; lexical live-fact check failed |
| wm-018 | fail | correctly refused silent upgrade; platform-version facts are not supported by product documents |

The full original answers, retrieved evidence, citations, checks, and receipts
are preserved in
`examples/business/customer-manager/amsylj01/acceptance/amsylj01-real-evaluation-20261102.json`.

## Authority and publication checks

Formal workbench operations now resolve identity from a trusted server-side
session resolver. Browser bodies cannot choose the operator, source authority,
reviewer, or publisher. Formal mode rejects synthetic identities. Source
activation, approval, and publication require distinct roles; optional
separation of duties rejects the producing operator as reviewer.

Quality approval v0.3 binds Candidate, validation, Quality Admission, source,
index, product, target revision, reviewer, approval time, and expiry. Publication
requires an explicit effective-source event and rejects expiry, revocation,
wrong version, changed admission, and replay. It no longer activates a source
implicitly.

The real REJECT Candidate could not be approved because its legacy validation
and Quality Admission did not pass. Its Candidate-specific Manifest count stayed
zero. A copied negative database confirmed unauthorized source activation is
FORBIDDEN and an effective source revocation returns
`SOURCE_SUPERSEDED_OR_REVOKED`.

## Workbench and deployment boundary

The existing workbench can load the fixed AMSYLJ01 sample and display its three
sources, 24 evidence units, provenance digest, and 18-case quality set. Formal
model evaluation remains disabled by default. PR #13 must receive independent
review, merge, controlled deployment, and authenticated Host integration before
the formal workbench may invoke real evaluation services.

No formal product, existing Manifest, history, Harness, Builder, PR #9 service,
or Shanghai environment was changed. The isolated services were stopped after
the run and the isolated SQLite database passed `PRAGMA integrity_check`.

