# AMSYLJ01 业务质量收口验收

结论：**REJECT，不审批、不发布、不生成 Manifest**。

## 真实隔离运行

- 真实 OpenJiuwen + DeepSeek 完成：25 题。
- Core 验证类型：`CORE_CORRELATED_FACTORY_WORKER`。
- 自动评价正确或正确拒答：12/25。
- 自动评价失败：13/25（wm-002-c1-suitability, wm-003-assessment-expiry, wm-004-three-month-liquidity, wm-008-fees, wm-009-principal-guarantee, wm-011-early-termination-distinction, wm-013-large-redemption, wm-016-current-customer-rating, blind-003-rating-change-redemption, blind2-001-zero-fees-scope, blind2-002-friday-late-redemption, blind2-003-partial-redemption-discretion, blind2-004-product-rule-not-customer-result）。
- 检索门禁失败：7/25（wm-004-three-month-liquidity, wm-016-current-customer-rating, blind-001-redemption-arrival, blind-003-rating-change-redemption, blind2-001-zero-fees-scope, blind2-003-partial-redemption-discretion, blind2-004-product-rule-not-customer-result）。
- 保留真实模型失败回执：2 份；最终成功运行未覆盖失败记录。

## 指标

| 指标 | 结果 |
|---|---:|
| Recall@3 | 86.95% |
| Hit@1 | 73.91% |
| MRR | 81.88% |
| 无答案误报 | 0.00% |
| 自动事实准确 | 66.03% |
| 自动引用准确 | 82.35% |
| 禁止性结论 | 100.00% |

自动指标不替代独立业务复核；业务复核及同口径 Before/After 见 `analysis/BUSINESS-QUALITY-CLOSEOUT.md`。

原始回答、引用证据、来源位置、requestId、traceId、模型回执和 Core 检查见同名 JSON。
