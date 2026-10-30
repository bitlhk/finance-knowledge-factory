# M0 合同与实现边界

## 1. 状态与对象

| 对象 | 标识与不变量 | 实际入口 |
|---|---|---|
| Source Revision | id + revision 唯一；UTF-8 内容摘要；只接文本；不宣称生效 | `register_source` |
| Source Activation | 独立权威事件；有生效日、状态和权威引用；不接受同日覆盖或乱序插入 | `activate_source` |
| Draft Recipe | 保存新 revision，只有草稿 head 改变 | `save_recipe` |
| Candidate | 固定 Recipe、测试集、资产摘要；不允许绑定正式读取 | `create_candidate` |
| Validation | 服务内部执行冻结金标；保存逐项 actual/expected；不能提交 passed=true 代替运行 | `validate_candidate` |
| Approved Artifact | 不改资产正文；Approval 固定候选、验证、范围、覆盖台账、审核人 | `approve` |
| Published Manifest | 发布不可变对象；审批不自动发布；发布不自动切换绑定 | `publish` |
| Active Policy | 版本化当前策略，可独立撤权；Recipe 的意向角色不是实际授权 | `set_policy` |
| Runtime Binding | 只支持 PINNED；原子 CAS 切换，记录绑定版本及 Manifest 摘要 | `bind` |
| Receipt | 保存输入、可信上下文、策略、绑定、Manifest、证据和结果 | `consume` |
| Replay | 按当前历史权限和来源权限回读已保存结果，不执行规则 | `replay` |

所有对象按 tenant 分区。数据库对象禁止 UPDATE/DELETE；逻辑 id/revision 不能覆盖不同内容。SQL 数据库管理员仍属于信任边界，这不是防特权篡改的签名账本。

摘要算法是 SHA-256，规范化为 UTF-8 JSON、键排序、无空白分隔、禁止浮点。不冒充 RFC 8785/JCS。跨语言组件接入时必须增加相同字节测试向量或统一正式规范，不能直接套另一个 JSON 序列化器。

## 2. Rule IR 已实现安全子集

Schema 文件：`contracts/rule-ir-v0.1.schema.json`。`contracts.py` 为维护源，导出文件受版本控制，测试检查二者一致。

每个 RuleSet 包含固定词表、规则、来源引用、适用范围、例外和 unresolved。所有对象拒绝未知属性；Schema 校验之外还需 `validate_ir` 做类型、字段引用、日期、唯一 ID 及复杂度检查。独立调用 JSON Schema 验证不等于准入完成。

### 类型

- integer：仅 Python/JSON 真整数，明确拒绝 bool、浮点、数字字符串；最小/最大值来自词表。
- boolean：仅 true/false，不隐式转换 0、1、字符串。
- date：严格 YYYY-MM-DD 且日历合法；非法日期不归一化。
- enum：固定非空词表；未识别值 INVALID_INPUT。
- string：非空有界字符串，只允许等值与集合判断。
- decimal：**本轮尚未开放**，Schema 拒绝；不能先转浮点。需 M1 BigDecimal/缩放整数与 DMN 精度探针通过后再扩合同。

当前 Host 字段只开放 `business_date`，来自可信宿主；用户参数中传入该字段会被拒绝。地区、机构、产品、用途、时区同样由 BusinessContext 提供，不由模型填写。

### AST

```json
{
  "op": "years_at_least",
  "start": {"field": "registration_date"},
  "asOf": {"field": "business_date"},
  "years": 3,
  "anniversary": "FEB29_TO_FEB28"
}
```

支持 eq/ne/lt/lte/gt/gte、in、all/any/not 和上述周年比较。日期、整数可排序，布尔/枚举/字符串只支持等值或集合；不允许不同类型比较。深度最多 4，单条规则含例外最多 64 个表达式节点，集合最多 50，规则最多 100。周年数是 AST 中受 Schema 约束的整数，较评审草案的 TypedLiteral 写法做了最小简化，不增加表达能力。

闰日转非闰年的周年日为 2 月 28 日，这是明确的**合成演示口径**，用于真实产品之前需要业务确认。

判定为 INVALID_INPUT、UNKNOWN、NOT_APPLICABLE、REVIEW_REQUIRED、MET 或 NOT_MET；MET 只表示单项条件满足，不表示授信通过。

执行顺序：严格输入校验 → 缺可信适用维度 UNKNOWN → 范围核对 → unresolved REVIEW_REQUIRED → 所需字段缺失 UNKNOWN → 例外 → 主条件。不通过逻辑短路掩盖缺失字段。正式模拟服务还先核对当前授权、固定 Manifest、来源生效与产物适用范围。

## 3. 例外不能靠空数组自证

规则发布前要求完整来源覆盖台账。非空原文行必须有处理记录；建模行关联存在的规则及同源证据；未处理行、未解决例外、重叠台账或伪引用阻断审批。Coverage 的审核人和权威引用由可信 Actor 注入。

这能阻断**已声明或已识别**的未解决项，不能识别任意自然语言里被模型漏掉的例外。若人工也错误标成 NON_NORMATIVE，结构检查无法纠正其业务判断。因此 M1 仍须将“同句主条件＋特殊行业例外”作为独立抽取金标，并评估真实覆盖。当前不得宣称 LLM 抽取漏例外的风险已全部消除。

## 4. 授权与适用性

- 公共 API 不暴露；本库只接受可信宿主传入 Actor，提供可替换的认证后上下文边界。
- 管理操作使用宿主授权的显式 privilege，例如 source.activate、rule.approve、manifest.publish；不在材料或模型输出里读取。
- 数据读取由当前策略的 principal + resource + action 精确匹配，不支持通配符默认放行。
- consume、history、source_read 分别授权；服务许可不能替代依赖来源权限。
- 产品历史角色默认只能回放本人产生的回执；读取他人输入还需该条 receipt 的显式 history 授权，不能用产品角色隐式越权。
- 证据资产和规则资产都必须有地区、机构、产品、用途、时区及生效区间。缺上下文拒绝，越界不返回知识正文。
- 多来源产物整体要求全部来源有权限；没有实现未经独立审批的自动片段脱敏。
- 来源新版本只有 REGISTERED 含义，不改变旧正式读取。权威 ACTIVE/REVOKED 事件按可信业务日期生效，旧绑定与新来源不匹配时阻断，不静默选最新。
- 历史回放使用当前 history/source_read 权限，不要求旧来源当前仍生效；返回 NOT_EVALUATED，不能当作当前业务判断。
- 本轮使用合成身份进行库级隔离验证，不等同于两个真实账号、网关或银行 IAM 集成验收。

## 5. 发布与并发

Validation 固定 Candidate + TestSet；Approval 固定 Candidate + Validation + Scope + Coverage。修改草稿需要新候选和验证，不允许把旧结果接到新候选。旧快照继续按原绑定服务，不受草稿影响。

发布使用 SQLite 原子事务，Manifest 一旦保存不可改；绑定使用 expected_revision。两个独立连接对同一版本并发更新，只能一个成功。当前授权和来源有效性读取，与本次结果构造处于同一个串行化事务。

当前不支持跨分布式数据库事务、远程引擎原子部署、签名发布、服务撤回列表及自动版本路由。它们不是 SQLite 测试已经证明的能力。

## 6. 与 Harness 的接缝，尚未接线

固定参考主线 `e911c71bdd3404f450bf775f32ebe028f90fb475`，复用 QUERY、BoundFinanceProvider、受管 Provider Factory、可信业务时间和 Assembler Lock，不能假定这些已经包含文档级 ACL。

M3 计划新增通用查询合同：`knowledge.evidence.query` 和 `knowledge.rule.evaluate`，配置固定服务连接及产品/Manifest 绑定。实际身份、用途、业务日期来自宿主；产品由安装配置白名单限制；不得允许模型任意填 URL、principal 或 Manifest。

Provider 回包应校验实际 manifestDigest 与安装绑定一致，附 source/evidence/rule digest、scope、decision、serviceReceiptId、traceId。知识 UNKNOWN 放在业务结果 decision 中，不为适配 Harness 的顶层 UNKNOWN 捏造 TASK 引用。Lock 需关联知识合同、Provider 版本、Manifest 和允许的绑定策略。

以上是下一阶段接入合同草案，本轮没有新增 Harness Capability、Provider 或安装 Lock，也没有启动 Java Runtime。
