# M2 网页真实接线：网页到 Core 通过，Harness H1a 未完成

日期：2026-10-30。独立分支 `feat/m2-web-core-h1a`，基于 PR #5 的 `b7c0e99`。
网页可执行代码验收基线：`72b8caf`。本报告及证据为后续提交，不回写旧报告。

## 已完成的实际操作

浏览器通过冻结 V1.5 的四个入口、三栏车间和四步配方完成：

上传合成 HTML → 配置三题检索集 → 新生产任务 → 真实 RAGFlow 索引及检索 →
Core 候选/验证 → 单独的隔离测试审批 → 不可变 Manifest 与绑定 → 原文证据查询。

- 原型 SHA-256 仍为 `a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80`。
- 运行：`run-39d069d400924257a857cfa7ec64917b`。
- Manifest：`8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`。
- 3/3 用户提供的合成检索题命中期望条款。这不是 30 题独立质量验收，也不是真实银行认可。
- RAGFlow dataset/document/build 身份、固定镜像、BGE 模型标识、原文及锚点均在保存记录中。
- 生成式模型调用 0 次；使用了真实本地 Embedding。费用仍为未知，不填零。
- 候选未审批时发布按钮禁用；未绑定时服务查询拒绝。公开的正式业务发布仍不可用。
- 网页不另存“已发布”标志，读取 Core 的 Manifest 与 binding；发布后显示的验证和审批
  也读取该 Manifest 固定的版本，不因后来验证记录改变。原始 job 文件仅保存生产证据。
- 发布确认只复用已保存的审批依据，不接受新说明冒充原审批。
- 来源/服务/历史读取权限仍由 Core 检查；UI 的可信身份、用途、日期由服务端固定。

## 测试结果与范围

| 验证 | 结果 | 不能替代什么 |
| --- | --- | --- |
| 最终 UI 上传、四步配方、生产、审批、绑定、查询 | 通过，真实 RAGFlow，三题 3/3 | 不代表任意文档质量通过 |
| 故障：停止本轮独占 RAGFlow API | 返回 `RAGFLOW_UNAVAILABLE`，不展示旧答案冒充成功 | 不代表所有分布式故障已验收 |
| API 停止期间刷新、读取已保存回执 | 通过，无新检索请求 | 不代表用户账号隔离验收 |
| 恢复 API 后重新查询 | 通过 | 不代表 OS 资源已全部回收 |
| 重启新预览进程后读取先前 Manifest/回执 | 通过，原任务不重跑 | 不代表生产级高可用 |
| 390px / 320px 首页 | 无整页溢出、无页面 JS 错误，截图保留 | 不代表所有设备已测 |
| Core/HTTP 定向测试 | 7 项通过：幂等、失败保留、审批/身份伪造拒绝、撤权、来源隔离、发布冻结等 | 非真实 IAM |
| 全量 Python 回归 | 最终 326 项通过，包含两项保存证据完整性检查 | 不代表 Harness 安装或 M1 语义验收 |

证据目录：`evidence/m2-web/`，包含两轮正常路径、故障与恢复截图、响应、14 个主要
Core 不可变对象以及逐文件摘要。首轮故障脚本错误地匹配了已存在的回执 DOM，
在停止 API 前发生 `TypeError`；失败截图保留，修正为等待本次 HTTP 响应后才断言。
后续两轮故障测试通过，未删除或覆盖第一次失败证据。

## 访问与演示

新入口仅监听 **127.0.0.1:61353**。原 61352 / 61351 不变，未修改反向代理或生产服务。

远程访问沿用 SSH 身份，在自己的终端增加：

```sh
ssh -N -L 61353:127.0.0.1:61353 ubuntu@111.119.236.165
```

浏览器打开 `http://localhost:61353/`。

1. 在“知识生产”查看已保存的 M2 浏览器合成客服制度，或上传本仓库
   `tests/fixtures/m2-document.html`。
2. 配置配方，选择文档知识，导入 `tests/fixtures/m2-ui-questions.json`，保存并开始生产。
3. 检查工序、原文位置和三题验证结果。规则产线本轮不可选。
4. 点击“隔离测试审批”，填写依据并确认测试范围，再单独“生成并绑定隔离快照”。
5. 到“知识产物”查询知识；到“知识消费”查看回执，展开核对版本与原文位置。

当前是单操作员回环测试入口，不是公网、多用户或正式审批系统。
每个任务使用独立知识产品 ID，最多 20 个生产任务；失败任务不自动重试，索引/证据保留，
没有声称自动清理全部资源。真实账号接入和知识产品多来源更新均不在本轮范围。

## 运行与停止

工作区 `/home/ubuntu/worktrees/knowledge-factory-m2-web`。
状态 `/home/ubuntu/outputs/knowledge-m2-web`；不包含正式配置或客户材料。
新预览和本轮 Embedding 进程由 `m2.preview_control` 记录 PID/启动身份，只停止自己创建的进程。

```sh
cd /home/ubuntu/worktrees/knowledge-factory-m2-web
/home/ubuntu/worktrees/knowledge-factory-web-production/.venv/bin/python \
  -m m2.preview_control stop --state /home/ubuntu/outputs/knowledge-m2-web
```

此命令不停止 Docker 容器。八个 `kf-m1-ragflow_*_1` 容器是既有独占测试栈，本轮重新启动，
为了网页复验保持运行。API/admin 只在回环端口，Embedding 只在私有 Docker bridge。
它们没有安装开机常驻；需要关闭整套实验时只停止该项目容器，不停止 Docker 或其他服务。
不会删除状态、索引、旧运行或评分。

## H1a：仍是开发缺口，不能宣布端到端

Harness 跟进分支 `feat/knowledge-h1a-evidence` / `bd7244b` 已新增 evidence-only 包，
并用未修改的 Builder `9d33295` 调用真实受管构建入口。结果仍为：

`ASSEMBLY_PROVIDER_CONNECTION_MISMATCH`，候选目录未创建、安装 Lock 为空、Agent UI 未调用。

代码复核还确认：构建准备仍创建 `http://127.0.0.1:1` 占位连接，未接知识配置摘要；
运行授权仍走 BankAccess；现有场景 SPI 的 `installationProviders` 尚未贯通准备阶段。
因此不能仅增加连接允许列表。详见 Harness 的 `providers/knowledge-service/H1A-STATUS.md`
及真实拒绝回执。

下一步只补 H1a 必要接线：锁定知识配置与连接身份、独立可信授权供应器、Core 协议适配、
受管安装/观测资格和现有 Agent 页面薄适配。随后用本次 Manifest 实测。
H1b 银行与知识联合装配另外验收。两项未通过前，M2 整体保持未验收。

PR #1 的语义质量门禁、PR #5 的后台证据、M0 Core 及 V1.5 产品结构均未改变。
本轮只提交独立 Draft 候选，不合并、不部署生产。
