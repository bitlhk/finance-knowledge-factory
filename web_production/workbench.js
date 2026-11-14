'use strict';
// Presentation only: existing commands, receipts and release authorities remain unchanged.
let publishedProducts = [], publishedLoaded = false, publishedError = false;
const previousRender = render;
const previousSourceView = sourceView;
const previousConsumeView = consumeView;
const previousArtifactsView = artifactsView;
const publicReadOnly = () => state?.accessMode === 'PUBLIC_READ_ONLY';
const publicationNotice = () => '<p class="boundary">开发环境发布记录，不代表银行销售授权。访问权限与来源有效性在实际查询时重新检查。</p>';
const publicationRows = (actionLabel = '查看产物') => publishedProducts.map(p => `<tr><td><strong>${E(p.title)}</strong><small>${E(p.code)} · 固定版本 ${E(p.revision)}</small></td><td>${p.sources.length} 份 PDF / ${p.pageCount} 页</td><td><span class="wb-status">质量通过</span><small>${p.caseCount} 道归档评测题 · 非完整业务覆盖</small></td><td>开发环境已发布<small>不代表银行生产授权</small></td><td><button class="btn secondary" data-publication="${E(p.code)}">${actionLabel}</button></td></tr>`).join('');
function publicationTable() {
  if (!publishedLoaded) return '<p role="status">正在核对发布记录…</p>';
  if (publishedError) return '<p role="alert" class="error-strip">发布记录暂时无法核验，请稍后重试。未将此状态视为未发布。</p>';
  if (!publishedProducts.length) return '<p class="hint">尚未接入可核验的发布记录。</p>';
  return `<div class="wb-table"><table><thead><tr><th>知识产品</th><th>原始资料</th><th>质量结果</th><th>发布状态</th><th>操作</th></tr></thead><tbody>${publicationRows()}</tbody></table></div>${publicationNotice()}`;
}
function taskList() {
  return state.runs.length ? `<div class="wb-table"><table><thead><tr><th>生产任务</th><th>运行状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody>${state.runs.map(r => `<tr><td>${E(r.title)}</td><td>${E(label(r.status))}</td><td>${E(new Date(r.createdAt).toLocaleString())}</td><td><button class="btn secondary" data-run="${E(r.id)}">查看任务</button></td></tr>`).join('')}</tbody></table></div>` : '<p class="hint">暂无生产任务。</p>';
}
productionHome = function () {
  if(publicReadOnly())return `${heading('知识生产','知识生产','候选加工、质量验证、审批与发布分别记录。','<button class="btn" disabled title="工作台 SSO 尚未接入">登录后开放</button>')}
    <ol class="wb-steps"><li>选择原料</li><li>配置配方</li><li>运行生产</li><li>验证候选</li></ol>
    <section class="wb-section"><h2>暂无可公开的生产任务</h2><p>当前是只读演示。上传、生产、评测、来源生效、审批和发布须在受权维护环境执行。</p><p class="boundary">历史测试任务保留在维护工作区，不会根据浏览器上次选择自动打开。已发布版本请进入“知识产物”查看。</p></section>`;
  return `${heading('知识生产', '知识生产', '固定原料版本，生产候选，验证后再审批与发布。', '<button class="btn" data-do="new-product">新建生产任务</button>')}
    <ol class="wb-steps"><li>选择原料</li><li>配置配方</li><li>运行生产</li><li>验证候选</li></ol>
    <section class="wb-section"><h2>当前生产任务</h2>${taskList()}</section>
    <details class="wb-legacy" id="workspace-tasks"><summary>工作区生产记录与失败记录（${state.runs.length}）</summary><p class="muted">加工完成不等于质量通过；历史测试与失败记录完整保留。</p>${taskList()}</details>
    <details class="wb-legacy"><summary>工作区已有原料（${state.sources.length}）</summary><div class="wb-materials">${state.sources.map(s => `<article><h3>${E(s.title)}</h3><p>${s.clauses.length} 个原文单元 · ${sourceRuns(s.id).length} 次生产</p><button class="btn secondary" data-product="${E(s.id)}">进入生产</button></article>`).join('') || '<p>请先上传原始资料。</p>'}</div></details>`;
};
sourceView = function () {
  return `${heading('知识原料', '已归档的基金原文', '按基金查看资料概要与招募说明书。', publicReadOnly()?'<button class="btn" disabled title="工作台 SSO 尚未接入">上传原料 · 登录后开放</button>':'<button class="btn" data-do="upload">上传 HTML 原料</button>')}
    ${publishedProducts.map(p=>`<details class="wb-source-group"><summary><strong>${E(p.title)}</strong><span>${E(p.code)} · ${p.sources.length} 份资料 · ${p.pageCount} 页</span></summary><div class="wb-materials">${p.sources.map(s => `<article><h3>${s.sourceId.endsWith('summary') ? '基金产品资料概要' : '招募说明书'}</h3><p>${s.pageCount} 页 · 原件摘要已核验</p><div class="actions"><a class="btn secondary" href="${E(s.officialUrl)}" target="_blank" rel="noopener noreferrer">官方原文</a><button class="btn secondary" data-publication="${E(p.code)}">查看页码与加工结果</button></div>${detail('文件校验信息', {file:s.file,sha256:s.sha256})}</article>`).join('')}</div></details>`).join('')}
    <p class="boundary">受权维护入口当前支持 HTML；PDF 使用已登记的受控加工流程，尚非通用 PDF 上传。</p>${publicReadOnly()?'':`<details class="wb-legacy"><summary>历史测试记录（${state.sources.length} 份原料）</summary>${previousSourceView()}</details>`}`;
};
artifactsView = function () {
  return `${heading('知识产物', '知识产物', '先查看内容与适用范围，再按需展开质量证据和版本。')}${publicationTable()}
    ${publicReadOnly()?'':`<details class="wb-legacy"><summary>旧工作区快照与生产来源</summary>${previousArtifactsView()}</details>`}`;
};
consumeView = function () {
  return `${heading('知识消费', '知识消费', '已发布知识通过受授权的财富助手查询。')}
    <section class="wb-section"><h2>财富助手 · 授权查询</h2><p>在 DSH 的灵感财富助手中登录灵感后查询产品知识。服务逐次核对身份、产品版本与授权范围。</p><a class="btn secondary" href="https://registry.linggan.top/" target="_blank" rel="noopener noreferrer">打开插件仓库</a></section>
    <section class="wb-section"><h2>网页验证查询</h2><p>工作台身份接入尚未完成，暂不开放匿名查询。原文与 PDF 页码仍可在“知识产物”查看。</p><button class="btn secondary" disabled>登录后开放</button></section>
    <section class="wb-section"><h2>装配与调用记录</h2><p class="boundary">Agent 装配清单和实时调用统计尚未接入。员工私人会话与查询回执不对匿名用户公开；不会以发布记录代替消费成功证据。</p></section>
    ${publicReadOnly()?'':`<details class="wb-legacy"><summary>旧工作区查询与保存回执</summary>${previousConsumeView()}</details>`}`;
};
workView = function () {
  if (!workshopOpen) return productionHome();
  const s = src();
  const nodes = [['source','原始资料'],['parse','条款解析'],['anchors','来源定位'],['documents','条款知识'],['retrieval','检索验证'],['validation','候选验证']];
  return `${heading('知识生产 / 当前任务', s?.title || '新生产任务', '加工、质量验证、审批和发布分别记录。', `<button class="btn secondary" data-do="catalog">返回列表</button><button class="btn" data-do="start" ${!s||!recipe||busy||activeRun()?'disabled':''}>开始生产</button>`)}
    <div class="wb-toolbar"><button class="btn secondary" data-do="choose">选择原料</button><button class="btn secondary" data-do="recipe" ${!s?'disabled':''}>配置配方</button><button class="btn secondary" data-do="tests" ${!s?'disabled':''}>测试集</button></div>
    <div class="progressline"><span>${recipeSummary()}</span>${badge(run?label(run.status):'尚未运行')}<select id="run-select" class="selector" aria-label="生产记录"><option value="">新生产任务</option>${sourceRuns(sourceId).map(r=>`<option value="${E(r.id)}" ${r.id===run?.id?'selected':''}>${E(label(r.status))} · ${E(new Date(r.createdAt).toLocaleString())}</option>`).join('')}</select></div>
    <section class="wb-section"><h2>生产过程</h2><div class="wb-flow">${nodes.map(([id,title]) => `<button data-step="${id}" class="${selection===id?'selected':''}"><strong>${title}</strong><small>${id==='source'?(s?'已登记':'未选择'):stage(id)?E(label(stage(id).status)):'查看记录'}</small></button>`).join('')}</div></section>
    ${inspector()}${productionChecks()}${run?.error?`<div role="alert" class="error-strip">${E(errors[run.error]||run.error)}</div>`:''}
    ${run?detail('技术证据：配方与阶段记录', {runId:run.id,recipe:run.recipe,stages:run.stages}):''}`;
};
render = function () {
  previousRender();
  if (!state) return;
  $('.brand-sub').textContent = 'KNOWLEDGE FACTORY';
  $('.sidebottom').textContent = publicReadOnly()?'公开只读演示 · 写操作未开放':'开发工作区 · 固定版本与原始证据保留';
  const inTask = workshopOpen && page==='production';
  $('#product-select').hidden = !inTask;
  const productLabel = $('.topcontrols .textmuted');
  if(productLabel){productLabel.hidden=!inTask;productLabel.textContent='当前生产原料';}
  document.querySelectorAll('.wb-table table').forEach(table => {
    const headers=[...table.querySelectorAll('th')].map(x=>x.textContent);
    table.querySelectorAll('tbody tr').forEach(row=>[...row.children].forEach((cell,i)=>cell.dataset.label=headers[i]));
  });
  $('.versiontag').textContent = workshopOpen && run && page==='production'
    ? (run.release?.state==='ISOLATED_PUBLISHED'?'开发快照已发布':'生产记录：'+label(run.status))
    : publicReadOnly()?'公开只读':'开发环境';
  document.querySelectorAll('[data-publication]').forEach(b => b.onclick = () => action(async () => {
    const p = await api('/api/published-products/' + encodeURIComponent(b.dataset.publication));
    dialog(p.title, `<p>${E(p.code)} · 固定版本 ${E(p.revision)} · ${p.pageCount} 页原文</p>${publicationNotice()}
      <div class="wb-facts"><div><b>质量验证</b><p>${p.caseCount} 道归档题通过</p></div><div><b>审批方式</b><p>${p.approvalMode==='MAINTENANCE'?'受权本机维护审批':'SSO 审批'}</p></div><div><b>发布范围</b><p>${p.productionAuthorized?'记录已包含生产授权':'开发环境，不是银行生产授权'}</p></div></div>
      <h3>原文与页码映射</h3><select id="published-page" aria-label="原文页码">${p.pages.map((x,i) => `<option value="${i}">${E(x.sourceId)} · PDF 第 ${x.page} 页</option>`).join('')}</select><p id="published-location" class="muted"></p><pre id="published-text" class="wb-original"></pre>
      ${detail('适用范围与内容边界',p.applicability)}${detail('质量检查明细',p.checks)}${detail('技术证据：Candidate、质量、审批与 Manifest', {candidateDigest:p.candidateDigest,qualityAdmissionDigest:p.qualityAdmissionDigest,approvalDigest:p.approvalDigest,manifestDigest:p.manifestDigest,metricsBps:p.metricsBps})}`);
    const select = $('#published-page');
    const show = () => {const x=p.pages[Number(select.value)];$('#published-text').textContent=x.text;$('#published-location').textContent=`PDF 第 ${x.page} 页 · HTML 位置 ${x.htmlId}（内部定位，不是原文条款编号）`;};
    select.onchange=show;show();
  }));
};
api('/api/published-products').then(result => {publishedProducts=result.products;}).catch(() => {publishedError=true;}).finally(() => {publishedLoaded=true;render();});
