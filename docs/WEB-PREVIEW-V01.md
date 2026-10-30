# Web Preview V0.1：隔离只读候选

## 基线与边界

- 独立分支 `feat/web-preview-v01`，基于 M1 固定提交 `a91add94038d03f6c46aa067135b98b99cd7f85a`。
- V1.5 原件存于 `web_preview/baseline/v1.5.html`，原始 SHA-256：
  `a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80`。
- CSS 从该原件提取，再增加只读预览及可读性规则；不运行原型中的模拟生产、审批、发布 JavaScript。
- 保留四个一级入口、三栏车间和四步配方。配方为当次冻结配置查看，不是在线编辑器。
- 本轮不改 M0、M1 抽取器、金标、历史结果，不运行模型、RAGFlow 或 Flowable，不提供发布 API。
- Draft PR 叠加到 `feat/m1-component-probes`，只包含预览及其测试，不把 M1 自动合入 main。

## 启动与访问

在本 worktree 根目录执行：

```bash
python3 -m pip install -r requirements-test.txt
python3 -m web_preview.server --port 61351
```

浏览器打开 http://127.0.0.1:61351/ 。仅回环监听，不改 Nginx、不新增公网端口。
远程访问需自行 SSH 转发 `-L 61351:127.0.0.1:61351` 到该开发机。
前台启动用 Ctrl-C 停止；本次交付的后台进程及日志位置在交付消息中给出，不安装常驻服务。

## 演示路径

1. 默认知识生产 / P43-1：查看同一份真实历史原文、语义单元和候选状态。
2. 点击“原始锚点2”或语义单元“查看原文依据”：查看引用、原始 HTML XPath、字符范围、来源及引用摘要。
   派生行号不会显示为原文页码。完整原文仅以转义纯文本展示，不执行来源脚本。
3. 打开“查看冻结配方”，依次查看目标与来源、工艺与组件、测试与验证、交付与权限。
   保存和发布不可用；关闭或 Escape 返回。
4. 切换 P08-1，点击冻结验证：原 `SEMANTIC_ERROR` 保留；事后附加复核单独展开，不覆盖原判断。
5. 知识产物查看四份候选、完整文件摘要并下载固定证据快照。无已发布 Manifest。
6. 知识消费 / P43-1：原候选断言4/10、实际引擎0次；切到独立数值诊断，10/10、实际引擎5次。
   二者有不同制品身份；诊断通过不代表候选通过。其他条款不能误挂 P43 诊断结果。

## 数据完整性

读取 `evidence/m1-verified-lowering/INDEX.json` 的固定文件摘要（索引自身也固定SHA），
逐文件验证，并复用 `lowering_bundle.verify()` 检查来源原件、锚点、实际请求/响应、配方、IR、编译制品与绑定。
启动与每次快照请求都验证。缺失或变化返回503，页面显示证据不可用，不退回模拟数据。
候选初始 `ENGINE_PENDING` 快照与最终归档分开展示；完整回执保留原运行编号与定义/部署编号。
当前没有正式 Knowledge Runtime 或 Harness 调用，不将“历史证据读取”标为“实时执行”。

## 实测结果（2026-10-30）

- Python 回归：266 passed，其中预览新增4项；原262项持续通过。
- Playwright：1366×900、390×844、320×844，四入口、四配方步骤、锚点、失败状态、独立诊断与证据缺失通过。
- 已实际查看桌面和手机截图，无整页横向溢出、未捕获脚本错误或文字重叠。
- HTTP：POST发布405、任意路径404、缺证据503；CSP禁止外部脚本、iframe嵌入及任意连接。
- 已保存截图及浏览器结果至 `evidence/web-preview-v01/`。
- 复跑：`python3 -m pytest -q`；安装 Playwright/Chromium 后运行 `node web_preview/check-browser.cjs`。
  可通过 `PLAYWRIGHT_MODULE` 和 `CHROMIUM_PATH` 指定现有安装，不要求全局升级。

## 未验收

无新的语义质量结论、无真实生产或发布权限、无真实身份多用户服务、无 Harness Agent 安装。
本预览不是正式 UI 上线；未合并、未部署生产，不替代 M1/M2/M3 各自门禁。
