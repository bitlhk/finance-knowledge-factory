'use strict';
// V1.5 layout is reused; release state is read only from the Core API response.
window.m2 = {
  releaseLabel(){return {NO_CANDIDATE:'等待生产',REVIEW_REQUIRED:'验证未通过',VALIDATED:'验证通过，待测试审批',APPROVED:'已测试审批，待绑定',ISOLATED_PUBLISHED:'隔离快照已绑定'}[run?.release?.state]||'等待生产';},
  home(){
    return `${heading('KNOWLEDGE PRODUCTION / 工作台','知识生产','文档知识 · 隔离测试工作区','<button class="btn" data-do="new-product">＋ 新建试产</button>')}
    <div class="v15-hero"><div><strong>五条专业知识生产线</strong><small>当前执行：文档知识</small></div><div class="v15-icons">${crafts.map((c,i)=>`<span class="v15-token ${i===0?'active':''}">${E(c)}</span>`).join('')}<button class="btn secondary sm" data-do="crafts">工艺目录</button></div></div>
    <div class="v14-summary"><b>${state.sources.length}</b> 份原料 · <b>${state.runs.length}</b> 次生产 · <b>${state.isolatedReleases.length}</b> 个隔离快照</div>
    <section class="pending-section"><div class="sectiontitle">生产记录</div>${state.runs.slice(0,5).map(r=>`<div class="v14-task"><div><b>${E(r.title)}</b><div class="small textmuted">${E(label(r.status))} · ${E(new Date(r.createdAt).toLocaleString())}</div></div><button class="btn secondary sm" data-run="${E(r.id)}">查看记录</button></div>`).join('')||'<div class="hint">尚无生产任务</div>'}</section>
    <div class="sectiontitle">知识产品</div><div class="gridproducts">${state.sources.map(s=>`<article class="card prod v14-product"><div class="prodtop"><div class="prodicon">知</div>${badge('HTML 原料')}</div><div><div class="prodtitle">${E(s.title)}</div><div class="prodpurpose">${s.clauses.length} 条已定位原文</div></div><div class="prodfoot"><span class="small textmuted">${sourceRuns(s.id).length} 次生产</span><button class="btn sm" data-product="${E(s.id)}">打开车间 →</button></div></article>`).join('')}</div>`;
  },
  checks(){
    const r=run?.release||{}, valid=['VALIDATED','APPROVED','ISOLATED_PUBLISHED'].includes(r.state);
    const stateName=this.releaseLabel();
    return `<section id="production-checks" class="v14-checks"><div class="sectiontitle">候选验证与隔离发布</div><div class="v14-checkgrid"><div class="v14-check"><b>来源与索引</b><p>${run?.coreObjects?'Core 已登记，摘要已固定':'等待登记'}</p></div><div class="v14-check"><b>候选验证</b><p>${E(stateName)}</p></div><div class="v14-check"><b>知识服务</b><p>${r.state==='ISOLATED_PUBLISHED'?'固定 Manifest':'未绑定，不可查询'}</p><button class="btn secondary sm" data-do="sandbox" ${r.state!=='ISOLATED_PUBLISHED'?'disabled':''}>查询隔离快照</button></div></div>
    <div class="v14-releasebox"><span class="small textmuted">仅隔离测试审批，不代表银行制度获批。身份、用途及业务日期由测试宿主固定。</span><div class="actions"><button class="btn secondary" data-do="approve-document" ${!valid||r.approvalDigest?'disabled':''}>隔离测试审批</button><button class="btn" data-do="publish-document" ${!r.approvalDigest||r.state==='ISOLATED_PUBLISHED'?'disabled':''}>生成并绑定隔离快照</button>${run?'<button class="btn secondary" data-do="export">导出运行证据</button>':''}</div></div>${r.candidateDigest?detail('Core 审批、Manifest 与绑定',r):''}</section>`;
  },
  artifacts(){
    return `${heading('03 / KNOWLEDGE ARTIFACTS','知识产物','Core 隔离发布快照 · 非正式业务发布')}<div class="gridproducts">${state.isolatedReleases.map(r=>`<article class="card prod"><div class="prodtitle">${E(r.title)}</div>${badge('隔离快照已绑定')}<p>条款证据 · 固定来源与索引</p>${detail('发布版本与适用范围',r)}<button class="btn secondary" data-run="${E(r.runId)}">查看生产与来源</button><button class="btn" data-query-run="${E(r.runId)}">查询知识</button></article>`).join('')||'<div class="hint">尚无隔离发布快照</div>'}</div>`;
  },
  consume(){
    return `${heading('04 / KNOWLEDGE CONSUMPTION','知识消费','固定版本的文档证据查询')}<div class="twoCol"><section><div class="sectiontitle">隔离知识服务</div>${state.isolatedReleases.map(r=>`<div class="v14-releaseitem"><b>${E(r.title)}</b><p>固定 Manifest · ${E(r.manifestDigest.slice(0,12))}</p><button class="btn" data-query-run="${E(r.runId)}">查询知识</button></div>`).join('')||'<div class="hint">尚无隔离知识服务</div>'}<div class="hint">Harness Agent 安装与调用尚待独立验收。</div></section><section><div class="sectiontitle">当前生产记录的查询回执</div>${(run?.consumptionReceipts||[]).map(r=>`<div class="v14-releaseitem"><b>${E(r.query)}</b>${detail('保存的回执，不重新执行',r.receipt)}</div>`).join('')||'<div class="hint">尚无查询回执</div>'}</section></div>`;
  },
  sandbox(){
    return `<h3>${E(run?.title)}</h3><div class="notice">Core 固定快照 · 真实 RAGFlow 检索 · 原文证据，非生成式回答</div><form id="search-form"><div class="field"><label for="query">查询问题</label><input id="query" maxlength="300" required value="${E(queryResult?.query||'')}" placeholder="请输入制度相关问题"></div><button class="btn" ${run?.release?.state!=='ISOLATED_PUBLISHED'?'disabled':''}>查询知识</button></form>${queryResult?`<p>${queryResult.hits.length} 条原文证据</p>${queryResult.hits.map(h=>`<article class="asset-row"><h3>${E(h.clause)}</h3><div class="quote">${E(h.text)}</div>${detail('原文锚点',h.anchors)}</article>`).join('')}${detail('Core 查询回执',queryResult.receipt)}`:''}`;
  },
  release(command){
    const captured={runId:run.id,candidateDigest:run.release.candidateDigest};
    const publishing=command==='publish-document';
    dialog(publishing?'绑定隔离知识快照':'隔离测试审批',`<form id="release-form"><p>${E(run.title)}</p><div class="field"><label for="release-reason">${publishing?'已保存的测试审批依据':'测试审批依据'}</label><textarea id="release-reason" required maxlength="1000" ${publishing?'readonly':''}>${publishing?E(run.release.approvalReason):''}</textarea></div><label class="checkbox"><input id="release-confirm" type="checkbox" required>确认仅供隔离验证，不作为银行业务批准</label><button class="btn">确认</button></form>`);
    $('#release-form').onsubmit=e=>{e.preventDefault();const reason=$('#release-reason').value;action(async()=>{await api(command==='approve-document'?'/api/document-approve':'/api/document-publish',{...captured,reason});run=await api('/api/runs/'+captured.runId);state=await api('/api/state');$('#modal-root').replaceChildren();})};
  },
  bind(){
    document.querySelectorAll('[data-query-run]').forEach(b=>b.onclick=()=>action(async()=>{const r=state.isolatedReleases.find(r=>r.runId===b.dataset.queryRun);await openProduct(r.sourceId,r.runId);showSandbox();}));
    if(workshopOpen&&page==='production'){
      const technology=$('.v15-hero small');if(technology)technology.textContent='原生 HTML 锚点 · RAGFlow 索引与检索 · Core 验证';
      const output=$('.outcol .colhead .badge');if(output)output.textContent=run?.release?.state==='ISOLATED_PUBLISHED'?'隔离快照':'候选知识';
    }
  },
  wizard(step){
    if(step===0){const target=$('.modal select');if(target)target.options[0].textContent='文档条款证据候选';}
    if(step===1){$('#rules-check').disabled=true;$('#rules-check').checked=false;wizardDraft.rules=false;wizardDraft.clauses=[];
      $('#component-config').innerHTML='<div class="v14-config"><div class="v14-configtitle">文档知识组件</div><p>原生 HTML 锚点 → RAGFlow 真实解析与索引 → 检索验证 → Core 候选登记</p><p>固定 RAGFlow 镜像与 BGE 中文索引模型；PDF、Word、规则产线本轮不执行。</p></div>';}
    if(step===3){$('.wizardgrid').innerHTML='<div class="field"><label>交付用途</label><input readonly value="Core 隔离测试审批与发布"></div><div class="field"><label>版本策略</label><input readonly value="固定 Manifest，不自动跟随新上传"></div><div class="field"><label>消费身份</label><input readonly value="固定合成知识 Agent 身份"></div><div class="field"><label>审批身份</label><input readonly value="服务端隔离测试操作员"></div>';
      const hint=$('.modal .hint');if(hint)hint.textContent='当前仅单操作员回环工作区，非业务 IAM。验证通过后须单独审批和绑定，不自动发布。';}
  },
  crafts(){dialog('五条专业工艺',crafts.map((c,i)=>`<div class="v14-releaseitem"><h3>${E(c)}</h3><p>${i===0?'HTML 原文锚点、RAGFlow 索引检索、Core 隔离发布':'本轮不执行，不参与发布'}</p></div>`).join(''));}
};
Object.assign(errors,{DOCUMENT_NOT_PUBLISHED:'该候选尚未绑定隔离发布快照。',DOCUMENT_APPROVAL_REQUIRED:'请先完成隔离测试审批。',RETRIEVAL_GOLD_REQUIRED:'至少需要一条检索测试题。',DOCUMENT_ONLY_REQUIRED:'本轮仅开放文档知识。',RAGFLOW_UNAVAILABLE:'RAGFlow 暂不可用，未返回替代结果。'});
init();
