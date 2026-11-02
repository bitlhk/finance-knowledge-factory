# AMSYLJ01 18题逐题根因

本报告由冻结的原始回答、Retrieval Trace、引用、金标和原文锚点生成。
原始 REJECT 不覆盖；内部‘第几条’仅作旧索引标识，不作为银行原文编号。

## 分类统计

| 分类 | 数量 | 含义 |
|---|---:|---|
| A | 3 | 真实业务回答错误或不完整 |
| B | 7 | 关键知识未进入最终证据 |
| C | 1 | 证据已提供但模型理解或引用错误 |
| D | 12 | 业务回答正确但自动事实检查误判 |
| E | 7 | 金标、证据标注或权威来源边界需要业务复核 |

## 逐题结论

| 题目 | 分类 | 基线 | 正确来源位置 | 失败环节 | 验证标准 |
|---|---|---|---|---|---|
| wm-001-risk-level | A,B | ANSWER_FACT_ERROR | product-spec:风险揭示书/产品风险级别；product-spec:产品说明书/产品基本信息/投资者类型 | 风险级别和适合投资者的产品专属证据位于原始候选第6位以后，Top3被通用风险匹配与特别提示占据；模型据此错误判断产品风险级别未披露。 | Top3同时包含产品风险级别2和适合投资者类型；回答给出2级中低风险并保留当前销售要求核实边界。 |
| wm-002-c1-suitability | B,E | ANSWER_FACT_ERROR | investor-rights:第三部分/风险等级对应关系；product-spec:风险揭示书/适合购买的投资者 | 产品适合投资者证据未进Top3；三份公开资料也没有定义C1与谨慎型或低风险的代码映射，原金标把业务系统映射当作文档事实。 | 知识回答说明产品要求并明确缺少C1权威映射；联合业务系统后才允许完成适当性判断。 |
| wm-003-assessment-expiry | D,E | ANSWER_FACT_ERROR | sales-agreement:第四部分第九项；investor-rights:第二部分 | 回答对超过一年需重测的直接问题正确，引用也正确；逐字检查不接受转述。金标额外要求说明有效期内重大变化，超出了本题最小结论。 | 一年/12个月和重新评估均由引用支持；错误期限或省略重测结论仍失败。 |
| wm-004-three-month-liquidity | A,B | ANSWER_FACT_ERROR | product-spec:产品基本信息/交易日与赎回到账；product-spec:第五部分/申购和赎回；product-spec:产品基本信息/提前终止 | 正常申赎及T+1证据没有进入Top3，模型把客户无权提前终止整个计划误解为不能正常赎回。 | 回答明确交易日可正常赎回、T+1及节假日顺延，同时说明不能保证三个月后的实际可用日。 |
| wm-005-weekend-order | B,D | ANSWER_FACT_ERROR | product-spec:第五部分/受理时间与挂单时间；product-spec:产品基本信息/交易日 | 挂单条款已召回且回答正确，但交易日定义未进Top3；逐字检查不接受“周末属于非交易日”和“下一受理时间自动成交”的等价表达。 | 引用同时覆盖非交易日和下一受理时间；不得承诺下一个自然日或周末到账。 |
| wm-006-minimum-subscription | D,E | ANSWER_FACT_ERROR | product-spec:第一部分/初次申购起点金额；product-spec:第五部分第5项 | 第十五内部单元已完整包含首次1万元和追加1000元，回答正确；旧金标又要求内容重复的第五内部单元，且逐字检查误判。 | 金额任一错误均失败；一份完整产品说明证据足以支持结论时不因重复引用缺失误判。 |
| wm-007-partial-redemption | D | ANSWER_FACT_ERROR | product-spec:第五部分第5项 | 回答与引用完整正确，旧检查仅因未逐字复制两句金标而失败。 | 9000份场景说明管理人有权强制全部赎回；错误说必然保留或必然部分赎回必须失败。 |
| wm-008-fees | A,B,D | ANSWER_FACT_ERROR | product-spec:第一部分/产品费率；product-spec:第三部分；product-spec:第五部分第6项 | 回答正确给出申赎费、0.2%和0.03%，但未召回完整费用及税费单元，遗漏相关税费条件；旧检查也未识别“无申购费”的等价表达。 | 完整列出各费用及税费边界；任何错误百分比、声称完全无费用或漏掉税费均失败。 |
| wm-009-principal-guarantee | D,E | ANSWER_FACT_ERROR | product-spec:风险揭示书/风险揭示内容；product-spec:特别提示；sales-agreement:第二部分 | 不保本、不保证收益及历史/预期收益不构成承诺的结论正确；旧检查不接受转述，并强制要求三份存在重叠的证据。 | 任何保本、收益保证或银行兜底结论均失败；正确否定必须有产品原文支持。 |
| wm-010-non-own-funds | D,E | ANSWER_FACT_ERROR | sales-agreement:第四部分第一项；investor-rights:风险提示 | 不得借款购买的业务结论和投资者权益引用正确；旧检查未识别自有资金与禁止非自有资金的逻辑等价，并要求重复协议证据。 | 回答必须明确不得使用贷款等非自有资金；任何正向许可均失败。 |
| wm-011-early-termination-distinction | B,C | ANSWER_FACT_ERROR | product-spec:产品基本信息/提前终止；product-spec:第五部分/申购和赎回 | 模型正确指出两个概念不同，但正常申购赎回条款未进入Top3，导致其错误声称现有原文没有主动赎回约定。 | 回答同时引用提前终止和每个交易日开放申购赎回，不得声称客户完全不能赎回。 |
| wm-012-bank-termination | D | ANSWER_FACT_ERROR | product-spec:产品基本信息/提前终止 | 通知、5个交易日变现、分配顺序和不计息均回答正确且引用正确，旧逐字检查全部误判。 | 三个关键条件及引用齐全；错误天数或承诺当日到账必须失败。 |
| wm-013-large-redemption | D | ANSWER_FACT_ERROR | product-spec:第五部分第7项 | 回答和唯一证据正确，旧逐字检查误判。 | 不得回答当天一定受理或暂停等于永久拒绝。 |
| wm-014-document-conflict | D | ANSWER_FACT_ERROR | sales-agreement:第一部分 | 回答与引用完全正确，旧逐字检查误判。 | 必须回答以产品说明书为准；反向优先级失败。 |
| wm-015-current-sale-status | 通过 | CORRECT_REFUSAL | 非产品文档权威 | 原回答正确拒绝，属于实时产品系统依赖，不是知识检索失败。 | 不得从历史公开资料推断今日在售、额度充足或停售。 |
| wm-016-current-customer-rating | B,D,E | ANSWER_FACT_ERROR | product-spec:风险揭示书/适合购买的投资者 | 最终拒绝客户适配结论正确，但产品专属适合投资者证据未召回；客户当前等级、有效期和销售要求属于CRM/产品系统，不应由知识库证明。 | 知识服务出站不含客户身份；联合Agent在业务系统事实齐备前不得给适合/不适合结论。 |
| wm-017-current-yield | D | ANSWER_FACT_ERROR | product-spec:第一部分/预期年化投资收益率 | 回答正确区分历史示例与今日收益并要求核实公告，引用正确；旧检查未识别该等价限制。 | 不得把2025-03-01示例当作今日收益；必须提示核实当前公告。 |
| wm-018-version-change | E | ANSWER_FACT_ERROR | 非产品文档权威 | 问题询问Factory的Manifest固定与升级机制，产品文件不是权威来源；将其纳入中行产品知识质量会导致错误引用和错误评价。 | 由Factory合同测试证明固定Manifest、重新评测审批发布和禁止静默升级。 |

完整原始答案、原文锚点、事实检查和修复建议见同目录 JSON。
