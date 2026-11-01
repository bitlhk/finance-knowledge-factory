# Finance Knowledge Factory

## 主线合并准备候选

本分支从 `main` 独立拆取固定候选 `160aaf5` 的已验收工程范围，尚未合并、部署或开启生产功能。
按 A 来源锚点、B 文档 Core/RAGFlow、C Runtime 查询与历史、D V1.5 隔离页面四个提交评审。
规则抽取与 Wiki 实验不进入可执行范围；原始失败记录和证据完整保留。

请先阅读 [合并范围、依赖与验收报告](docs/MAIN-CONVERGENCE-REVIEW.md) 和
[本轮执行证据](evidence/main-preparation/summary.json)。隔离网页须显式启动，不能直接作为生产 IAM／审批服务。
以下保留原始 M0 基线说明。会写入 `evidence/` 的旧示例命令只应在独立测试副本执行，避免覆盖归档。

## 原始 M0 基线

金融可信知识工厂：规划五条专业知识产线，首期聚焦文档知识与业务规则，通过标准知识服务对接 Finance Harness。

当前公开基线为 **Knowledge Core V0.1 · M0 工程候选**，不是已完成的五条真实产线。

V1.5 产品架构冻结。本仓库只实现首期合同、安全状态边界和可重复的合成回归，不修改原 HTML、Finance Harness、Builder 或线上服务。

**状态：M0 工程候选。不是生产服务，不是 Flowable 联调，不是业务准入证明。**

## 本轮可运行内容

- `contracts/`：Rule IR、来源版本与生效事件、Recipe、资产、候选、测试集、验证、覆盖台账、审批、Manifest、当前权限与 Runtime Binding 的 JSON Schema。
- `knowledge_core/rules.py`：严格类型、真实日历、结构化适用范围、有限 AST、缺失及例外处理的参考语义。没有 eval、外部函数、任意脚本或网络调用。
- `knowledge_core/core.py`：SQLite 不可变对象、原子事务、绑定 CAS、当前权限复核及保存结果回放。
- `examples/m0_smoke.py`：经营贷条件核验、纯 FAQ 两类合成产品共用同一 Core，不按产品 ID 分支。
- `tests/`：冻结的 26 条规则断言，加合同、生命周期、安全及并发回归。

## 运行

本次已用 Python 3.12.3、jsonschema 4.10.3、pytest 7.4.4 验证。建议在独立虚拟环境安装锁定依赖；以下命令均在本仓库执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m knowledge_core.contracts
.venv/bin/python -m tools.freeze_inventory
.venv/bin/python -m pytest -q --junitxml=evidence/m0-tests.xml
.venv/bin/python -m examples.m0_smoke
```

本机本轮使用已安装的相同版本，没有联网安装依赖或创建后台进程。示例只使用临时 SQLite，测试后自动删除数据库，JSON 回执保留在 `evidence/`。不需要模型密钥，不启动端口。

## 必须理解的限制

1. 所有 Manifest、调用回执强制 `M0_REFERENCE_ONLY`。当前不允许把该参考解释器当作正式规则引擎；Flowable 编译及执行一致性是 M1 门禁。
2. `Actor`、`BusinessContext` 由未来可信宿主提供，不能接受用户 JSON 直接反序列化。当前是授权接口契约与隔离测试，不是实际银行 IAM、真实账号隔离验收。
3. 完整覆盖台账、来源定位及声明的 `unresolved` 可以校验；**不能自动证明自然语言例外没有被抽取遗漏**。人工覆盖确认与 M1 独立抽取金标仍不可缺。
4. Decimal、币种/单位换算、自由表达式、PDF/OCR、自动选择最新版本均未开放，明确拒绝。月份等字段范围来自合成词表，不是银行统一阈值。
5. FAQ 只验证证据摘要、原文行号及受控读取，不包含真实解析、向量检索或回答质量测试。
6. 这里只处理登记和权威生效事件。Watcher、异步任务取消、重加工、完整服务撤回、历史留存、备份与部署加固属于 M1/M2，不伪装成已实现。

## 文档

- [合同与实现边界](docs/CONTRACTS.md)
- [M0 验收和后续门禁](docs/M0-REPORT.md)
- [实施基线与下一阶段](docs/BASELINE.md)

公开仓库：<https://github.com/bitlhk/finance-knowledge-factory>。

公开版源自本地 M0 提交 `3a3339e9f0cbf90fc539c3086b6d58644a9ce3a0` 的脱敏快照；来源提交保留在原始开发仓库，不属于公开 Git 历史。代码、合同、合成样本和金标保持原样，详见 [公开基线说明](docs/PUBLICATION.md)。

未部署应用服务。后续集成需固定版本并评审，不复制修改现有 Harness 公共授权链路。开源许可证待仓库维护者确定，本次未擅自添加许可证。
