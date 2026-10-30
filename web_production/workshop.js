'use strict';
// V1.5 structure, connected only to the isolated production API. No prototype simulation.
let workshopOpen = false, selection = 'parse';
const E = escapeHtml;
const badge = (text, tone = '') => `<span class="badge ${tone}">${E(text)}</span>`;
const heading = (ey, title, description, actions = '') => `<div class="heading"><div><div class="eyebrow">${E(ey)}</div><h1 class="h1">${E(title)}</h1><p class="sub">${E(description)}</p></div><div class="actions">${actions}</div></div>`;
const crafts = ['文档知识','事实关系','业务规则','流程方法','案例经验'];
const hasRules = () => run ? Boolean(run.recipe.rulePipeline) : Boolean(recipe?.rules);
const sourceRuns = id => state.runs.filter(r => r.sourceId === id).sort((a,b)=>b.createdAt.localeCompare(a.createdAt));
const activeRun = () => run && !['COMPLETED','FAILED','PARTIAL','INTERRUPTED'].includes(run.status);
const stage = name => run?.stages.filter(s=>s.name===name).at(-1);
const stageBadge = name => badge(stage(name) ? label(stage(name).status) : '未执行', stage(name)?.status==='FAILED'?'gold':'');

function productionHome() {
  return `${heading('KNOWLEDGE PRODUCTION / 工作台','知识生产','知识产品试产 · 固定原料版本，配置加工工艺，生成并验证候选。', '<button class="btn" data-do="new-product">＋ 新建试产</button>')}
  <div class="v15-hero"><div><strong>五条专业知识生产线</strong><small>本轮接通文档知识与受限业务规则，其余工艺未接入。</small></div><div class="v15-icons">${crafts.map((c,i)=>`<span class="v15-token ${[0,2].includes(i)?'active':''}">${E(c)}</span>`).join('')}<button class="btn secondary sm" data-do="crafts">工艺目录</button></div></div>
  <div class="v14-summary"><b>${state.sources.length}</b> 个单来源试产产品 <span>·</span> <b>${state.runs.length}</b> 次生产记录 <span>·</span> <b>0</b> 个正式发布版本</div>
  <section class="pending-section"><div class="sectiontitle">待处理任务</div>${state.runs.length?state.runs.slice(0,3).map(r=>`<div class="v14-task"><div><b>${E(r.title)}</b><div class="small textmuted">${E(label(r.status))} · ${E(new Date(r.createdAt).toLocaleString())} · 未正式发布</div></div><button class="btn secondary sm" data-run="${E(r.id)}">查看记录</button></div>`).join(''):'<div class="hint">尚无生产任务</div>'}</section>
  <div class="sectiontitle">知识产品</div><div class="gridproducts">${state.sources.map(s=>{const rs=sourceRuns(s.id);return `<article class="card prod v14-product"><div class="prodtop"><div class="prodicon">知</div>${badge(rs.length?'候选待复核':'尚未生产','gold')}</div><div><div class="prodtitle">${E(s.title)}</div><div class="prodpurpose">条款知识与可选业务规则 · ${s.clauses.length} 条原文</div></div><div class="prodmeta">${badge('HTML 来源')}${badge('固定内容版本')}${badge('未核定业务适用范围')}</div><div class="prodfoot"><span class="small textmuted">${rs.length} 次生产 · 未发布</span><button class="btn sm" data-product="${s.id}">打开车间 →</button></div></article>`}).join('')}</div>
  ${state.sources.length?'':'<div class="hint">从原料库选择资料，或上传一份新的 HTML 制度开始试产。</div>'}`;
}

function workView() {
  if (!workshopOpen) return productionHome();
  const s=src(), a=run?.artifact;
  const lanes=[['文档知识','documents',[['anchors','原文定位'],['documents','条款知识'],['retrieval','检索验证']]]];
  if(hasRules())lanes.push(['业务规则','rules',[['semantic','语义识别'],['lowering','受控转换'],['validation','质量验证']]]);
  return `${heading('02 / KNOWLEDGE PRODUCTION',s?.title||'新知识产品试产','固定来源与配方 → 专业加工 → 候选知识 → 验证与复核',`<button class="btn secondary" data-do="catalog">← 产品列表</button><button class="btn secondary" data-do="tests" ${!s?'disabled':''}>测试集</button><button class="btn" data-do="start" ${!recipe||!s||busy||activeRun()?'disabled':''}>开始生产知识</button>`)}
  <div class="progressline"><span>${recipeSummary()}</span>${badge(run?label(run.status):'尚未启动', 'gold')}<span>${run?'保存的真实运行 · '+E(new Date(run.createdAt).toLocaleString()):'配方草稿'}</span><select id="run-select" class="selector" aria-label="生产记录"><option value="">新生产任务</option>${sourceRuns(sourceId).map(r=>`<option value="${r.id}" ${r.id===run?.id?'selected':''}>${E(label(r.status))} · ${E(new Date(r.createdAt).toLocaleString())}</option>`).join('')}</select></div>
  <div class="v15-hero"><div><strong>当前生产工艺与技术配置</strong><small>原生 HTML 定位${hasRules()?' · 火山引擎 DeepSeek · 受控 Rule IR 转换':''} · 候选验证</small></div><button class="btn secondary sm" data-do="crafts">工艺目录</button></div>
  <div class="workbench"><section class="card workcol"><div class="colhead"><b>① 原始资料</b></div><div class="v14-inlinebar"><button class="btn secondary sm" data-do="choose">从原料库选择</button><button class="btn secondary sm" data-do="upload">＋ 上传资料</button></div>
  ${s?`<button class="sourcetile ${selection==='source'?'on':''}" data-step="source"><b>${E(s.title)}</b><small>HTML · 固定来源版本 · ${s.clauses.length} 条款</small></button>`:'<div class="hint">尚未绑定原料</div>'}<div class="small textmuted">${s?'来源已登记；权威生效与适用范围尚未核定。':'本次试产支持一份 HTML 来源。'}</div></section>
  <section class="card workcol"><div class="colhead"><b>② 加工过程</b>${badge(run?'冻结配方':'配方草稿','red')}</div><div class="v14-inlinebar"><button class="btn secondary sm" data-do="recipe" ${!s?'disabled':''}>配置配方</button><button class="btn secondary sm" data-do="components" ${!s?'disabled':''}>工艺组件</button></div><button class="processintro ${selection==='parse'?'on':''}" data-step="parse"><b>公共接入与结构解析</b><span class="small textmuted">固定来源、编号条款与原文位置</span>${stageBadge('parse')}</button><div class="procdown">↓ 按配方执行</div>
  ${lanes.map(([title,key,steps])=>`<div class="lane"><div class="lanetitle"><strong>${title}流水线</strong>${stageBadge(key)}</div><div class="steprow">${steps.map(([id,name],i)=>`${i?'<span class="stepsep">›</span>':''}<button class="workstep ${selection===id?'on':''}" data-step="${id}">${name}</button>`).join('')}</div></div>`).join('')}
  ${!hasRules()?'<div class="hint">业务规则未选择；可在配方中增加受限规则抽取。</div>':''}</section>
  <section class="card workcol outcol"><div class="colhead"><b>③ 本次产出</b>${badge(a?'未审批候选':'尚无产物','gold')}</div><div class="outlist"><button class="outputtile" data-step="documents"><span class="count">${a?.documentClauses.length??0} 条</span><b>条款知识</b><p>${E(a?.documentClauses[0]?.text.slice(0,85)||'等待本次加工')}</p></button>${hasRules()?`<button class="outputtile" data-step="semantic"><span class="count">${a?.rules.length??0} 组</span><b>业务规则候选</b><p>条件、适用关系、例外与人工前提</p></button>`:''}<button class="outputtile" data-step="validation"><b>质量报告</b><p>${run?E(label(run.status))+'，不等于语义质量通过':'尚未执行'}</p></button></div><button class="btn secondary sm" data-do="checks">检查 / 复核 / 发布 ↓</button></section></div>
  ${inspector()}${productionChecks()}${run?.error?`<div role="alert" class="risk">${E(errors[run.error]||run.error)}</div>`:''}
  ${run?detail('运行标识、冻结配方与阶段记录',{runId:run.id,recipe:run.recipe,recipeDigest:run.recipeDigest,stages:run.stages}):''}`;
}

function inspector() {
  const clauses=run?.artifact?.documentClauses||src()?.clauses||[];
  const c=clauses.find(c=>c.clause===activeClause)||clauses[0];
  const r=run?.artifact?.rules.find(r=>r.clause===c?.clause);
  const attempt=run?.attempts.find(t=>t.clause===c?.clause);
  const titles={source:'原始资料',parse:'公共接入与结构解析',anchors:'原文定位',documents:'条款知识',retrieval:'检索验证',semantic:'语义识别',lowering:'受控转换',validation:'质量验证'};
  let out='', check='';
  if(['source','parse','anchors','documents'].includes(selection)){
    out=c?`<div class="kv"><span>条款</span><span>${E(c.clause)}</span></div><div class="kv"><span>原文位置</span><span>${c.anchors.length} 处真实 HTML 定位</span></div><div class="raw">${E(c.text)}</div>${detail('定位技术详情',c.anchors)}`:'<div class="hint">尚无条款</div>';
    check=`<div class="${run?.artifact?'good':'hint'}">${run?.artifact?'本次生产已校验原文锚点。':'导入定位已完成，生产任务尚未生成产物。'}</div><p class="small textmuted">来源登记与定位不代表权威生效、真实性或业务适用性已确认。</p>`;
  }else if(selection==='retrieval'){
    const tests=run?.artifact?.validation?.retrievalTests||[];
    out=tests.length?tests.map(t=>`<div class="itemrow"><span>${E(t.question)}</span>${badge(t.passed?'命中期望条款':'未命中','gold')}</div>`).join(''):'<div class="hint">未配置检索测试，不计通过</div>';
    check='<div class="hint">当前为原文关键词检索，不是 RAGFlow 服务检索，也不生成问答。</div>';
  }else if(['semantic','lowering'].includes(selection)){
    out=r?(selection==='semantic'?r.semantic.units.map(u=>`<div class="candidate-result">${badge(label(u.state),'gold')}<div class="quote">${E(u.quote)}</div>${u.branchQuote?`<small>适用对象：${E(u.branchQuote)}</small>`:''}</div>`).join(''):r.projection.decisions.map(d=>`<div class="candidate-result">${badge(label(d.status),'gold')}<div class="quote">${E(d.quote)}</div></div>`).join('')):`<div class="hint">${attempt?.status==='FAILED'?'抽取失败，原始记录已保留':run?'此条款未生成规则候选':'尚未执行'}</div>`;
    check=`<div class="warn">${r?(r.projection.ir?.rules.length||0)+' 项数值子条件完成受控转换。':'无已验证的数值子条件。'}整条制度仍待复核，不构成业务审批结论。</div>${r?detail('语义、关系、IR 与编译制品',r):''}${attempt?detail('本次真实模型调用记录',attempt):''}`;
  }else{
    out=run?.artifact?`<div class="kv"><span>原文定位</span><span>回查完成</span></div><div class="kv"><span>语义完整性</span><span>未验收</span></div><div class="kv"><span>生产阶段规则执行</span><span>未提供事实，未执行</span></div>`:'<div class="hint">尚无本次验证记录</div>';
    check=`<div class="warn">未审批、未发布；隔离测试回执与生产阶段检查分别记录。</div>${run?.artifact?detail('原始验证结果',run.artifact.validation):''}`;
  }
  return `<section class="card inspect"><div class="inspecttop"><div><h3>${E(titles[selection])}</h3><span class="small textmuted">${run?'本次保存的真实生产记录':'原料与配方草稿'}</span></div><select id="clause-select" class="selector" aria-label="查看条款">${clauses.map(x=>`<option ${x.clause===c?.clause?'selected':''}>${E(x.clause)}</option>`).join('')}</select></div><div class="inspectthree"><div class="inspectpane"><b>原始输入 / 来源证据</b><div class="raw">${E(c?.text||'尚无原料')}</div></div><div class="inspectpane"><b>加工结果 / 知识对象</b>${out}</div><div class="inspectpane"><b>质量检查 / 后续处理</b>${check}</div></div></section>`;
}

function productionChecks(){
  return `<section id="production-checks" class="v14-checks"><div class="sectiontitle">候选验证与发布</div><div class="v14-checkgrid"><div class="v14-check"><b>原文与结构检查</b><p>${run?.artifact?'已执行，原始结果可查':'等待生产'}</p></div><div class="v14-check"><b>独立语义验收</b><p>未验收，不允许发布</p></div><div class="v14-check"><b>候选隔离测试</b><p>${run?.consumptionReceipts?.length||0} 条保存回执</p><button class="btn secondary sm" data-do="sandbox" ${!run?.artifactDigest?'disabled':''}>打开候选测试</button></div></div><div class="v14-releasebox"><span class="small textmuted">本预览无正式审批与发布权限，未通过的候选与失败记录保留。</span><div class="actions"><button class="btn secondary" disabled title="尚未接入业务审核">提交审核</button><button class="btn" disabled title="本预览不提供正式发布接口">发布知识产品</button>${run?'<button class="btn secondary" data-do="export">导出运行证据</button>':''}</div></div></section>`;
}

function artifactsView(){
  return `${heading('03 / KNOWLEDGE ARTIFACTS','知识产物','正式发布的知识产品')}<div class="v14-summary"><b>0</b> 个已发布产品</div><div class="hint">尚未接通正式发布。生产得到的候选、验证结果与失败记录保留在对应车间。</div><button class="btn secondary" data-do="workshop">返回当前生产车间</button>`;
}

function consumeView(){
  return `${heading('04 / KNOWLEDGE CONSUMPTION','知识消费','正式知识服务与消费记录')}<div class="twoCol"><section><div class="sectiontitle">已发布知识服务</div><div class="hint">尚无正式发布的知识服务。Finance Harness 接入仍独立验收。</div><div class="actions"><button class="btn secondary" disabled>调用正式服务</button><button class="btn secondary" data-do="workshop">返回候选车间</button></div></section><section><div class="sectiontitle">当前候选测试历史</div>${(run?.consumptionReceipts||[]).map(r=>`<div class="v14-releaseitem"><b>${r.query?'条款检索':'数值子条件测试'}</b><p class="small">${E(r.query||label(r.decision))} · ${E(new Date(r.createdAt).toLocaleString())}</p>${detail('保存的回执（不重新执行）',r)}</div>`).join('')||'<div class="hint">当前未选择有测试回执的生产记录</div>'}</section></div>`;
}

async function openProduct(id, runId){
  sourceId=id; recipe=null; run=null; queryResult=testResult=null; activeClause=null;
  const chosen=runId||sourceRuns(id)[0]?.id;
  if(chosen){run=await api('/api/runs/'+chosen);restoreResults();localStorage.setItem('production-run',run.id);}
  else localStorage.removeItem('production-run');
  workshopOpen=true;page='production';selection='parse';
}

function bindWorkshop(){
  document.querySelectorAll('[data-product]').forEach(b=>b.onclick=()=>action(()=>openProduct(b.dataset.product)));
  document.querySelectorAll('[data-run]').forEach(b=>b.onclick=()=>action(()=>openProduct(state.runs.find(r=>r.id===b.dataset.run).sourceId,b.dataset.run)));
  document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>{selection=b.dataset.step;render()});
  if($('#clause-select'))$('#clause-select').onchange=e=>{activeClause=e.target.value;render()};
  if($('#product-select'))$('#product-select').onchange=e=>action(()=>openProduct(e.target.value));
}

function craftDialog(){
  dialog('五条专业工艺', `<div class="v15-panel"><div class="v15-craftnav">${crafts.map((c,i)=>`<button class="v15-craft-btn" data-craft="${i}"><b>${c}</b><small>${[0,2].includes(i)?'受限接通':'未接入'}</small></button>`).join('')}</div><div class="v15-detail" id="craft-detail"></div></div>`);
  const descriptions=[['HTML 原生定位','编号条款、原文锚点、关键词检索。RAGFlow / PDF / Word 未接入本页面。'],['事实关系','OpenSPG / Graphiti 处于规划，不可运行。'],['DeepSeek + 受控转换 + Flowable','个人贷款期限字段词表；每次最多两条。规则执行需单独输入合成事实；不能把子条件满足当作整条通过。'],['流程方法','方法包与流程工艺未接入，不可运行。'],['案例经验','案例结构化与相似案例检索未接入，不可运行。']];
  const choose=i=>{$('#craft-detail').innerHTML=`<h3>${crafts[i]}</h3><strong>${descriptions[i][0]}</strong><p>${descriptions[i][1]}</p>`;document.querySelectorAll('[data-craft]').forEach(b=>b.classList.toggle('sel',b.dataset.craft===String(i)))};
  document.querySelectorAll('[data-craft]').forEach(b=>b.onclick=()=>choose(Number(b.dataset.craft)));choose(0);
}

init();
