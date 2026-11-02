# AMSYLJ01 业务质量改进验收

结论：**REJECT，不发布 Manifest**。工程指标改善不等于业务发布合格。

## Before / After

| 指标 | 原18题基线 | v0.2（17原题+4盲测） |
|---|---:|---:|
| Recall@3 | 37.50% | 78.94% |
| Hit@1 | 68.75% | 68.42% |
| MRR | 77.08% | 80.70% |
| 无答案误报 | 50.00% | 0.00% |
| 事实准确 | 7.69% | 68.18% |
| 引用准确 | 51.72% | 81.48% |
| 禁止性结论 | 100.00% | 100.00% |

## 结果

- 正确回答或正确拒答：9/21（wm-001-risk-level, wm-006-minimum-subscription, wm-007-partial-redemption, wm-010-non-own-funds, wm-012-bank-termination, wm-014-document-conflict, wm-015-current-sale-status, blind-001-redemption-arrival, blind-004-channel-live-state）。
- 检索仍失败：8/21（wm-002-c1-suitability, wm-007-partial-redemption, wm-008-fees, wm-011-early-termination-distinction, wm-013-large-redemption, wm-016-current-customer-rating, blind-001-redemption-arrival, blind-003-rating-change-redemption）。
- 原始答案、原文引用、来源位置、requestId、traceId 和模型回执摘要见同名 JSON。
- 原 v0.1 REJECT、原18题和原索引未覆盖；本次没有审批、发布或 Manifest。
