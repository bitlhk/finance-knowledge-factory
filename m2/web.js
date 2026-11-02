'use strict';
// V1.5 layout is reused; release state is read only from the Core API response.
window.m2 = {
  async startDemo(){
    await action(async()=>{
      const html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>合成客服制度</title></head><body><h1>合成客服制度，仅供隔离测试</h1><p>第一条 合成客服服务时间为每日09:00至17:00。</p><p>第二条 客户申请历史对账单时，应在合成客服窗口提交申请。</p><p>第三条 信息缺失时，应交由人工核实，不得编造缺失信息。</p></body></html>';
      const source=await api('/api/sources',{title:'合成客服制度 · 文档生产体验',html});
      state=await api('/api/state');sourceId=source.id;run=null;recipe=null;queryResult=testResult=null;
      activeClause=null;selection='parse';workshopOpen=true;page='production';
      localStorage.removeItem('production-run');
      wizardDraft={sourceId,rules:false,clauses:[],modelConsent:false,tests:[
        {question:'合成客服服务时间是什么？',expectedClause:'第一条'},
        {question:'客户如何申请历史对账单？',expectedClause:'第二条'},
        {question:'信息缺失时如何处理？',expectedClause:'第三条'}]};
      wizard=0;showWizard();
    });
  },
  async startBusinessSample(){
    await action(async()=>{
      const loaded=await api('/api/business-samples/boc-amsylj01',{});
      state=await api('/api/state');sourceId=loaded.source.id;run=null;recipe=null;queryResult=testResult=null;
      activeClause=null;selection='parse';workshopOpen=true;page='production';
      localStorage.removeItem('production-run');
      wizardDraft={sourceId,rules:false,clauses:[],modelConsent:false,tests:loaded.tests};
      wizard=0;showWizard();
    });
  },
  nextAction(){
    if(!src())return null;
    if(activeRun())return ['','生产进行中'];
    if(run?.release?.state==='ISOLATED_PUBLISHED')return ['sandbox','查询本次知识产物'];
    if(run?.release?.state==='APPROVED'&&!run?.release?.sourceActivationDigest)return ['activate-document-source','确认来源生效'];
    if(run?.release?.state==='APPROVED')return ['publish-document','发布固定版本'];
    if(run?.release?.state==='QUALITY_PASSED')return ['approve-document','审批发布'];
    if(run?.release?.state==='EVALUATION_REQUIRED')return state.modelReady?['evaluate-document','运行质量评测']:['checks','查看评测准备情况'];
    if(run)return ['checks','查看本次验证结果'];
    return recipe?['start','开始生产知识']:['recipe','配置生产配方'];
  },
  releaseLabel(){return {NO_CANDIDATE:'等待生产',REVIEW_REQUIRED:'候选验证未通过',EVALUATION_REQUIRED:'候选就绪，待质量评测',EVALUATION_RUNNING:'质量评测执行中',EVALUATION_FAILED:'质量评测执行失败',QUALITY_REJECTED:'质量未通过',QUALITY_PASSED:'质量通过，待独立审批',APPROVED:'已审批，待发布',ISOLATED_PUBLISHED:'固定版本已发布'}[run?.release?.state]||'等待生产';},
  home(){
    return `${heading('KNOWLEDGE PRODUCTION / 工作台','知识生产','文档知识 · 隔离测试工作区','<button class="btn" data-do="boc-business-sample">载入中行 AMSYLJ01 样本</button><button class="btn secondary" data-do="document-demo">体验合成样本</button><button class="btn secondary" data-do="new-product">＋ 新建试产</button>')}
    <div class="v15-hero"><div><strong>五条专业知识生产线</strong><small>当前执行：文档知识</small></div><div class="v15-icons">${crafts.map((c,i)=>`<span class="v15-token ${i===0?'active':''}">${E(c)}</span>`).join('')}<button class="btn secondary sm" data-do="crafts">工艺目录</button></div></div>
    <div class="v14-summary"><b>${state.sources.length}</b> 份原料 · <b>${state.runs.length}</b> 次生产 · <b>${state.isolatedReleases.length}</b> 个隔离快照</div>
    <section class="pending-section"><div class="sectiontitle">生产记录</div>${state.runs.slice(0,5).map(r=>`<div class="v14-task"><div><b>${E(r.title)}</b><div class="small textmuted">${E(label(r.status))} · ${E(new Date(r.createdAt).toLocaleString())}</div></div><button class="btn secondary sm" data-run="${E(r.id)}">查看记录</button></div>`).join('')||'<div class="hint">尚无生产任务</div>'}</section>
    <div class="sectiontitle">知识产品</div><div class="gridproducts">${state.sources.map(s=>{const m=s.metadata,b=s.businessProduct;return `<article class="card prod v14-product"><div class="prodtop"><div class="prodicon">知</div>${badge(b?'PDF＋HTML 固定来源':'HTML 原料')}</div><div><div class="prodtitle">${E(s.title)}</div><div class="prodpurpose">${s.clauses.length} 条已定位原文${b?` · ${b.sourceCount} 份官方资料 · ${b.qualityCaseCount} 道业务题`:''}</div></div>${m?`<div class="prodmeta">${badge(m.institution)}${badge(m.documentDate)}${badge(m.version)}</div><p class="small textmuted">${E(m.authorityStatus==='AUTHORIZED_INTERNAL_SOURCE'?'已授权内部来源':'办理时需核对现行状态')}</p>`:'<p class="small textmuted">来源适用状态尚未登记</p>'}${b?detail('来源摘要与固定加工版本',b):''}<div class="prodfoot"><span class="small textmuted">${sourceRuns(s.id).length} 次生产</span><button class="btn sm" data-product="${E(s.id)}">打开车间 →</button></div></article>`}).join('')}</div>`;
  },
  checks(){
    const r=run?.release||{}, evaluation=run?.qualityEvaluation||{}, report=evaluation.report;
    const caseRows=(report?.cases||[]).map(item=>{const passed=['CORRECT','CORRECT_REFUSAL'].includes(item.classification);return `<article class="v14-releaseitem"><div class="prodtop"><b>${E(item.caseId)}</b>${badge(passed?'通过':'未通过',passed?'':'gold')}</div><div class="quote">${E(item.answer||'未形成回答')}</div><p class="small textmuted">事实检查 ${(item.factChecks||[]).filter(v=>v.passed).length}/${(item.factChecks||[]).length} · 引用检查 ${(item.citationChecks||[]).filter(v=>v.passed).length}/${(item.citationChecks||[]).length}</p>${detail('回答引用、事实检查与失败原因',item)}</article>`}).join('');
    return `<section id="production-checks" class="v14-checks"><div class="sectiontitle">质量评测、审批与发布</div><div class="v14-checkgrid"><div class="v14-check"><b>来源与候选</b><p>${run?.coreObjects?'Core 已登记，摘要已固定':'等待登记'}</p></div><div class="v14-check"><b>质量评测</b><p>${E(this.releaseLabel())}</p><button class="btn secondary sm" data-do="evaluate-document" ${r.state!=='EVALUATION_REQUIRED'||!state.modelReady?'disabled':''}>运行质量评测</button></div><div class="v14-check"><b>知识服务</b><p>${r.state==='ISOLATED_PUBLISHED'?'固定 Manifest':'尚未发布'}</p><button class="btn secondary sm" data-do="sandbox" ${r.state!=='ISOLATED_PUBLISHED'?'disabled':''}>查询已发布版本</button></div></div>
    ${!state.modelReady?'<div class="hint">可信评测服务尚未接入当前工作台，页面与合同可验证，但不会启动真实模型调用。</div>':''}
    ${report?`<div class="sectiontitle">业务问题质量报告</div><div class="v14-summary"><b>${E(report.decision)}</b> · 事实准确率 ${E(String(report.metricsBps?.factAccuracy??0))}/10000 · 引用准确率 ${E(String(report.metricsBps?.citationAccuracy??0))}/10000</div>${caseRows}${detail('可信运行证据与质量门禁',report)}`:''}
    <div class="v14-releasebox"><span class="small textmuted">质量通过、来源生效、人工审批和发布是相互独立的受权动作。</span><div class="actions"><button class="btn secondary" data-do="activate-document-source" ${r.state!=='APPROVED'||r.sourceActivationDigest?'disabled':''}>确认来源生效</button><button class="btn secondary" data-do="approve-document" ${r.state!=='QUALITY_PASSED'?'disabled':''}>审批发布</button><button class="btn" data-do="publish-document" ${r.state!=='APPROVED'||!r.sourceActivationDigest?'disabled':''}>发布固定版本</button>${run?'<button class="btn secondary" data-do="export">导出运行证据</button>':''}</div></div>${r.candidateDigest?detail('Candidate、Admission、来源生效、审批与 Manifest',r):''}</section>`;
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
    const activating=command==='activate-document-source';
    const title=activating?'确认资料来源生效':publishing?'发布固定知识版本':'审批知识产品发布';
    const stored=publishing?run.release.approvalReason:'';
    dialog(title,`<form id="release-form"><p>${E(run.title)}</p><div class="field"><label for="release-reason">${publishing?'已保存的审批依据':activating?'来源生效依据':'审批依据'}</label><textarea id="release-reason" required maxlength="1000" ${publishing?'readonly':''}>${E(stored)}</textarea></div><label class="checkbox"><input id="release-confirm" type="checkbox" required>${activating?'确认当前来源版本在登记适用范围内生效':'确认操作绑定当前 Candidate、质量结果和目标版本，后续变更必须重新评测及审批'}</label><button class="btn">确认</button></form>`);
    $('#release-form').onsubmit=e=>{e.preventDefault();const reason=$('#release-reason').value;const endpoint=activating?'/api/document-source-activate':command==='approve-document'?'/api/document-approve':'/api/document-publish';action(async()=>{await api(endpoint,{...captured,reason});run=await api('/api/runs/'+captured.runId);state=await api('/api/state');$('#modal-root').replaceChildren();})};
  },
  evaluate(){
    const captured={runId:run.id,candidateDigest:run.release.candidateDigest};
    action(async()=>{
      await api('/api/document-evaluate',captured);
      for(let i=0;i<180;i++){
        await new Promise(resolve=>setTimeout(resolve,1000));
        run=await api('/api/runs/'+captured.runId);
        if(!['QUEUED','RUNNING'].includes(run.qualityEvaluation?.state))break;
      }
      state=await api('/api/state');
    });
  },
  bind(){
    document.querySelectorAll('[data-query-run]').forEach(b=>b.onclick=()=>action(async()=>{const r=state.isolatedReleases.find(r=>r.runId===b.dataset.queryRun);await openProduct(r.sourceId,r.runId);showSandbox();}));
    if(workshopOpen&&page==='production'){
      const next=this.nextAction();
      if(next){
        const button=document.createElement('button');button.className='btn';button.textContent=next[1];
        button.id='next-production-action';
        button.dataset.nextAction=next[0];button.disabled=busy||!next[0];button.onclick=()=>dispatch(next[0]);
        if(next[0]==='start')button.dataset.do='start';
        $('.heading [data-do="start"]').replaceWith(button);
      }
      const technology=$('.v15-hero small');if(technology)technology.textContent='原生 HTML 锚点 · RAGFlow 索引与检索 · Core 验证';
      const output=$('.outcol .colhead .badge');if(output)output.textContent=run?.release?.state==='ISOLATED_PUBLISHED'?'隔离快照':'候选知识';
    }
  },
  wizard(step){
    if(step===0){const target=$('.modal select');if(target)target.options[0].textContent='文档条款证据候选';}
    if(step===1){$('#rules-check').disabled=true;$('#rules-check').checked=false;wizardDraft.rules=false;wizardDraft.clauses=[];
      $('#component-config').innerHTML='<div class="v14-config"><div class="v14-configtitle">文档知识组件</div><p>原生 HTML 锚点 → RAGFlow 真实解析与索引 → 检索验证 → Core 候选登记</p><p>固定 RAGFlow 镜像与 BGE 中文索引模型；PDF、Word、规则产线本轮不执行。</p></div>';}
    if(step===3){$('.wizardgrid').innerHTML='<div class="field"><label>交付用途</label><input readonly value="业务知识质量评测与固定版本发布"></div><div class="field"><label>版本策略</label><input readonly value="固定 Manifest，不自动跟随新上传"></div><div class="field"><label>消费身份</label><input readonly value="由服务端授权策略确定"></div><div class="field"><label>审批方式</label><input readonly value="质量通过后独立审批"></div>';
      const hint=$('.modal .hint');if(hint)hint.textContent='评测、审批和发布相互独立；浏览器不能指定模型身份、质量结论或审批人。';}
  },
  crafts(){dialog('五条专业工艺',crafts.map((c,i)=>`<div class="v14-releaseitem"><h3>${E(c)}</h3><p>${i===0?'HTML 原文锚点、RAGFlow 索引检索、Core 隔离发布':'本轮不执行，不参与发布'}</p></div>`).join(''));}
};
Object.assign(errors,{DOCUMENT_NOT_PUBLISHED:'该候选尚未发布固定版本。',DOCUMENT_APPROVAL_REQUIRED:'请先完成独立发布审批。',QUALITY_ADMISSION_REQUIRED:'质量评测尚未通过。',EVALUATION_SERVICE_NOT_READY:'可信评测服务尚未接入当前工作台。',QUALITY_EVALUATION_BUSY:'质量评测正在执行。',RETRIEVAL_GOLD_REQUIRED:'至少需要一条检索测试题。',DOCUMENT_ONLY_REQUIRED:'本轮仅开放文档知识。',RAGFLOW_UNAVAILABLE:'RAGFlow 暂不可用，未返回替代结果。'});
init();
