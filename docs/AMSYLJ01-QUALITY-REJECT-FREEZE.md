# AMSYLJ01 quality REJECT freeze

The 29-case run, original answers, receipts, independent business review and
Quality Admission are frozen at PR #14 `b7691e6d87eee9f0b663cc21a6bdd28480777417`.
The authoritative artifact hashes are recorded in
`quality-reject-freeze-v0.4.json`. Existing gold answers, thresholds, failed
receipts and source evidence must not be rewritten.

Decision: **REJECT**. There is no Approval, publication attempt or Manifest.

## Five real business errors

### `wm-002-c1-suitability`

- Erroneous answer: “直接结论：不能购买”，并自行声称“C1对应谨慎型”。
- Correct boundary: the documents establish product risk level 2 and the
  listed suitable investor categories. They do not establish the bank's live
  C1 mapping, the customer's current valid assessment, or a completed
  suitability decision.
- Source: product specification/risk disclosure PDF page 1 and investor-rights
  risk-level material. The sales system remains authoritative for current
  mapping and customer status.
- Expected behavior: state the product facts, mark C1 mapping and the customer's
  final result unresolved, and request authorized live-system verification.

### `wm-004-three-month-liquidity`

- Erroneous answer: begins with “可以赎回” and “三个月后……资金T+1日到账”.
- Correct boundary: normal redemption differs from terminating the whole
  product, but a future redemption cannot be promised without the future
  trading calendar, product/channel state and any suspension condition.
- Source: product specification PDF page 7 for acceptance/T+1 and large
  redemption; page 5 for whole-product early termination.
- Expected behavior: explain the documented normal and exceptional rules, then
  explicitly withhold the future availability/date conclusion.

### `wm-007-partial-redemption`

- Erroneous answer: says the request “将导致” all remaining units to be forcibly
  redeemed, then later says the manager only “有权” and is not obliged.
- Correct boundary: falling below 10,000 units gives the manager a right to
  process a forced full redemption; it is not documented as an automatic or
  mandatory outcome.
- Source: product specification, fifth section item 5, PDF page 7.
- Expected behavior: preserve the discretionary wording consistently and do not
  state that forced redemption will occur.

### `blind2-002-friday-late-redemption`

- Erroneous answer: says a 15:40 request “可能需按挂单处理”.
- Correct boundary: 15:40 is outside the 8:30-15:30 acceptance window and before
  the 15:45 order window. It cannot be classified as an accepted or pending
  order from the document alone. T+1 also does not establish a fixed calendar
  date without an authorized calendar and current channel state.
- Source: product specification PDF pages 4, 5 and 7.
- Expected behavior: identify the uncovered five-minute interval, require live
  channel verification, and avoid a next-business-day promise.

### `blind3-002-large-redemption-recovery`

- Erroneous answer: says a large redemption trigger automatically suspends the
  same-day request.
- Correct boundary: the manager has the right to suspend same-day requests; if
  that right is exercised, applications continue on the next trading day.
- Source: product specification, fifth section item 7, PDF page 7.
- Expected behavior: keep both the discretion and the next-day continuation
  condition; do not turn the right into an automatic duty.

## Deferred evaluator work

Seven business-correct answers remain conservative automatic false negatives:
`wm-008`, `wm-016`, `blind2-001`, `blind2-003`, `blind2-004`, `blind3-003`, and
`blind3-004`. They are backlog evidence, not permission to relax thresholds or
change this frozen result. No further evaluator work belongs in PR #14.
