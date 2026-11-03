# AMSYLJ01 业务质量收口验收

结论：**REJECT，不审批、不发布、不生成 Manifest**。

## 真实隔离运行

- 真实 OpenJiuwen + DeepSeek 完成：29 题。
- Core 验证类型：`CORE_CORRELATED_FACTORY_WORKER`。
- 自动评价正确或正确拒答：17/29。
- 自动评价失败：12/29（wm-002-c1-suitability, wm-004-three-month-liquidity, wm-007-partial-redemption, wm-008-fees, wm-016-current-customer-rating, blind2-001-zero-fees-scope, blind2-002-friday-late-redemption, blind2-003-partial-redemption-discretion, blind2-004-product-rule-not-customer-result, blind3-002-large-redemption-recovery, blind3-003-zero-redemption-fee-tax, blind3-004-suitability-document-boundary）。
- 检索门禁失败：6/29（wm-016-current-customer-rating, blind-001-redemption-arrival, blind-003-rating-change-redemption, blind2-003-partial-redemption-discretion, blind2-004-product-rule-not-customer-result, blind3-004-suitability-document-boundary）。
- 保留真实模型失败回执：1 份；最终成功运行未覆盖失败记录。

## 指标

| 指标 | 结果 |
|---|---:|
| Recall@3 | 88.88% |
| Hit@1 | 85.18% |
| MRR | 90.12% |
| 无答案误报 | 0.00% |
| 自动事实准确 | 75.40% |
| 自动引用准确 | 92.68% |
| 禁止性结论 | 100.00% |

自动指标不替代独立业务复核；业务复核及同口径 Before/After 见 `analysis/BUSINESS-QUALITY-CLOSEOUT.md`。

原始回答、引用证据、来源位置、requestId、traceId、模型回执和 Core 检查见同名 JSON。
