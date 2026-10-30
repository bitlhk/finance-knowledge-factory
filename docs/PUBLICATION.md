# M0 公开基线说明

本仓库经维护者授权公开，名称为 `bitlhk/finance-knowledge-factory`。

## 来源和处理

- 来源为本地 M0 提交 `3a3339e9f0cbf90fc539c3086b6d58644a9ce3a0`，原始仓库与原始验收证据保留不动。
- 公开仓库从清理后的快照创建新的 Git 历史，避免开发环境标识进入旧提交后仍可见。
- `knowledge_core/`、`contracts/`、`tests/`、`examples/`、`tools/`、依赖和包配置与原 M0 逐文件保持一致。
- 公开副本移除文档中的开发机绝对路径，以及 JUnit XML 中的 hostname 属性；测试名称、数量、断言结果、耗时与时间戳没有改写。
- `evidence/m0-walkthrough.json` 中的主体、制度和业务数据全部为合成样例。没有真实银行材料、用户会话、访问凭据或运行数据库。
- 补充最小 GitHub Actions：安装锁定的直接依赖，检查 Schema 导出一致性，执行测试和合成演练。没有部署步骤或生产凭据。

## 基线与后续开发

`main` 用于可复跑的候选基线，`m0-candidate-v0.1` 标记公开的 M0 快照，不表示生产就绪。M1 探针应在新分支通过 PR 评审。

公开前做了凭据模式、地址/路径和人工内容检查；这不是专业安全审计，也不能替代后续依赖与代码审查。

公开可见不代表真实组件已经接通。M0 仍是 `M0_REFERENCE_ONLY`：RAGFlow、Docling、Flowable、真实模型、IAM 与 Harness 接入均需后续验收。

许可证由仓库维护者后续确定；本次没有自动选定 MIT、Apache 等许可证，也没有捆绑第三方项目源码。
