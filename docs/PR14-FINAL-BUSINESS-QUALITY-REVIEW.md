# PR #14 final business-quality review

This review closes the bounded AMSYLJ01 quality iteration. It does not approve
or publish the product and does not create a Manifest. The workbench PR remains
Draft.

## Fixed run and immutable evidence

- Model: Volcengine `deepseek-v4-flash` through OpenJiuwen.
- Candidate: `be5953e2632bc491fdc0857b0a94792ce0962605e40f0a8d438b26b7423f8fd9`.
- Test set: `96a41f73370934d5b181e4d2f1db56026b5a2d1a42b36d780677373850f9a738` (29 cases).
- Successful Assignment: `bb6b60783fd884c85a44a5e0b928bfb8cf5c7bb4c18248c7b18896da7bcc0fc9`.
- Successful Lease: `056ba647206af89c63870e1d21a2fab0f6eeb95a33dead23198a926783d4fb8f`.
- Runtime Evidence: `f5b90a04f95f9d3909a0bec9e8547dc031ee5d3a4d0edbfce1fb2ea201c0a0e1`.
- Answer Evaluation: `c84b46977d2e7ae7cfe226d32a8cbf69cc21779b5d969431ce0e96f3e0907248`.
- Quality Admission: `6562100573e0b1ef13a7f4096ea73fa45e4d32a05035fd220df69036a8933708` (`REJECT`).
- Retained failed model receipt:
  `872bb92d50d7d87e5e0fbbb6776e40e3c93e27a8b13492b367bf8eff448ac7a1`.

The successful Worker run took 248,820 ms. Its 29 returned model calls used
22,876 input tokens, 21,096 output tokens and 43,972 total tokens. Model latency
was 242,361 ms total, 8,357 ms mean, 4,844 ms median, 20,360 ms p95 and
39,704 ms maximum. The retained failed attempt made 10 returned calls and one
failed call before retry, using 12,689 recorded tokens. Total recorded usage
across both attempts was 56,661 tokens. Receipts do not contain an authoritative
price schedule, so no currency cost is inferred.

The first attempt failed at `wm-011` with `EVALUATION_SERVICE_REQUEST_INVALID`.
The successful retry used a fresh Assignment and Lease. No one-shot lease was
reused. Two earlier service-start failures caused by missing fixed-task fields
were also retained in the service journal and occurred before model execution.

## Four requested business cases

| Case | Evidence | Final business review | Automatic result |
| --- | --- | --- | --- |
| `wm-004` | normal redemption, T+1, large-redemption suspension and whole-product termination all retrieved | **Incorrect**: begins with a definite future redemption commitment before qualifying future product, calendar and channel state | rejected |
| `wm-013` | suspension right and next-trading-day continuation both retrieved and cited | **Correct**: preserves “has the right”, possible same-day suspension and next-day continuation | correct |
| `blind2-001` | zero subscription/redemption fees plus management, custody, floating management and possible tax evidence | **Correct** | false negative |
| `blind2-002` | exact 8:30-15:30 acceptance, 15:45 order start and T+1 evidence | **Incorrect**: says 15:40 may be handled as an order although that time is in neither window | rejected |

The new blind set found one additional real error: `blind3-002` treats the
manager's right to suspend same-day large redemptions as an automatic suspension.
`wm-002` still invents a C1 mapping/customer result, and `wm-007` contradicts
itself by saying forced redemption both will happen and is merely discretionary.
The independent business review is therefore 24/29 usable and 5/29 incorrect.

## Evaluator v0.3

The final deterministic evaluator now:

- recognizes locally scoped negation such as “not mandatory”, “not certain” and
  “the document does not state that the customer passed”;
- resets negation at a contrast clause, so “not stated, but the customer passed”
  remains a prohibited affirmative claim;
- rejects an unqualified “will result in forced redemption” while accepting the
  conditional “if the manager exercises the right”.

Paired positive/negative coverage also retains zero-fee scope, normal
redemption versus whole-product termination, T+1 versus same-day/fixed-date
claims, and product rules versus a completed customer suitability decision.

Replaying the immutable 29 archived answers with v0.3 produced:

| Result | Count |
| --- | ---: |
| True positive | 17 |
| False positive | 0 |
| False negative | 7 |
| True negative | 5 |

Fact accuracy is 75.40%, citation accuracy 92.68%, and forbidden-claim accuracy
100%. The fact score is lower than the pre-v0.3 77.04% because two contradictory
answers are now correctly rejected; no false positive was introduced to improve
the pass rate. Character-overlap support still causes seven conservative false
negatives and must not be read as business error count.

Retrieval for the 29-case run measured Recall@3 88.88%, Hit@1 85.18%, MRR
90.12%, zero no-answer false positives, and 84 ms average latency. The new
unseen set passed retrieval for three of four cases; the suitability-boundary
case still lacks all expected product evidence. No further retrieval tuning was
performed.

## Separate admission decisions

### A. Workbench engineering

The PR #14 code is suitable to enter formal code review after its final CI is
green. It is **not merge-ready yet** because it is stacked on PR #13, PR #13
still lacks an independent reviewer, and formal authenticated identity/service
integration remains a deployment prerequisite. This conclusion does not depend
on forcing AMSYLJ01 to PASS.

### B. AMSYLJ01 knowledge product

The product remains **REJECT**. Retrieval and answer checks do not satisfy the
unchanged quality thresholds, and five real business errors remain. There is no
approval, publication attempt or Manifest. The candidate must remain visible as
an unpublished quality candidate only.

## Compatibility and shutdown

The run used an isolated database and three isolated service identities. All
services were stopped after acceptance and SQLite `integrity_check` returned
`ok`. Existing products, Manifests, query/history contracts, Harness, Builder,
PR #9 and formal services were not modified.

Detailed original answers, citations, source pages, request/trace IDs and model
receipts are in
`examples/business/customer-manager/amsylj01/acceptance/amsylj01-business-quality-final-v04-20261102.json`.
The v0.3 replay and independent review mapping are in the adjacent `analysis`
files.
