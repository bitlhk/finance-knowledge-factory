'use strict';
const $ = s => document.querySelector(s);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const json = x => escapeHtml(JSON.stringify(x, null, 2));
let state, page = 'sources', sourceId, run, activeClause, tab = 'documents', errorText = '', busy = false;
let recipe = null, wizard = 0, queryResult = null, testResult = null;
const labels = {QUEUED:'排队中', RUNNING:'加工中', COMPLETED:'加工结束', PARTIAL:'部分完成',
  FAILED:'失败，记录已保留', INTERRUPTED:'执行中断，未自动重试', NOT_SELECTED:'未选择',
  REVIEW_REQUIRED:'待人工复核', MET:'数值子条件满足', NOT_MET:'数值子条件不满足',
  INVALID_INPUT:'输入不合法', UNKNOWN:'无法确认', NOT_APPLICABLE:'不适用',
  VERIFIED_NUMERIC:'受控转换已完成', UNSUPPORTED:'当前工艺不支持', UNVERIFIABLE:'待确认转换依据',
  MANUAL:'需人工确认', EXTERNAL:'缺少外部依据', PROPOSED_NUMERIC:'数值条件候选'};
const label = x => labels[x] || x;
const errors = {MODEL_CONNECTION_UNAVAILABLE:'模型连接未配置，条款产物已保留。',
  NO_VERIFIABLE_NUMBERED_CLAUSES:'未找到可定位的编号条款。本轮支持 UTF-8 HTML 的“第…条”制度正文。',
  RULE_SELECTION_LIMIT_TWO:'每次最多抽取两条完整条款，其余条款仍会生成文档知识。',
  PRODUCTION_BUSY:'已有生产任务正在执行，请等待结束。', MODEL_SCOPE_AND_CONSENT_REQUIRED:'请选择条款并确认发送到已配置模型。',
  CLAUSE_NOT_IN_SOURCE:'所选条款或测试题期望条款不属于当前原料。',
  MODEL_OUTPUT_INCOMPLETE:'模型输出不完整，未将截断内容转为规则。',
  SEMANTIC_ANCHOR_NOT_UNIQUE:'模型引用未能唯一对应原文，规则转换已阻断。'};
async function api(path, data) {
  const res = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const obj = await res.json();
  if (!res.ok) throw new Error(errors[obj.error] || obj.error || '请求失败');
  return obj;
}
async function action(fn) {
  if (busy) return;
  busy = true; errorText = '';
  try { await fn(); } catch (e) { errorText = e.message; }
  finally { busy = false; render(); }
}
const src = () => state.sources.find(s => s.id === sourceId);
const detail = (title, value) => `<details class="technical"><summary>${escapeHtml(title)}</summary><pre>${json(value)}</pre></details>`;
const status = s => `<span class="status-label">${escapeHtml(label(s))}</span>`;
function restoreResults(){const receipts=run?.consumptionReceipts||[];queryResult=receipts.filter(r=>r.id.startsWith('query-')).at(-1)||null;testResult=receipts.filter(r=>r.id.startsWith('test-')).at(-1)||null;}
function sourceView() {
  return `<div class="pagehead"><div><h1>知识原料</h1><p class="muted">来源版本 · 原文条款</p></div><div class="actions"><button class="btn" data-do="sample">导入公开制度样例</button><button class="btn primary" data-do="upload">上传 HTML</button></div></div>
  ${!state.sources.length ? '<div class="no-content">原料库为空</div>' : `<table class="source-list"><thead><tr><th>原料名称</th><th>已识别条款</th><th>导入时间</th><th></th></tr></thead><tbody>${state.sources.map(s => `<tr class="${s.id===sourceId?'selected':''}"><td>${escapeHtml(s.title)}<div class="subsource">${s.id.slice(0,12)} · 未核定权威生效</div></td><td>${s.clauses.length} 条</td><td>${escapeHtml(new Date(s.importedAt).toLocaleString())}</td><td><button class="btn" data-source="${s.id}">进入生产</button></td></tr>`).join('')}</tbody></table>`}
  ${src() ? detail('查看当前原料及定位', {title:src().title,sourceDigest:src().id,clauses:src().clauses}) : ''}`;
}
function recipeSummary() {
  const r = run?.recipe;
  if (r) return `${r.rulePipeline ? '文档知识 + 业务规则' : '文档知识'} · ${r.selectedClauses.length ? escapeHtml(r.selectedClauses.join('、')) : '不抽取业务规则'}`;
  if (recipe) return `${recipe.rules?'文档知识 + 业务规则':'文档知识'} · ${recipe.clauses.length} 条规则抽取`;
  return '尚未配置配方';
}
function workView() {
  const source = src(), a = run?.artifact;
  const clauses = a?.documentClauses || source?.clauses || [];
  const selected = clauses.find(c=>c.clause===activeClause) || clauses[0];
  const latest = name => run?.stages.filter(s=>s.name===name).at(-1);
  return `<div class="pagehead"><div><h1>知识生产车间</h1><p class="muted">${escapeHtml(source?.title || '尚未选择原料')}</p></div><div class="actions"><button class="btn" data-do="choose">从原料库选择</button><button class="btn" data-do="upload">上传 HTML</button></div></div>
  <div class="production-bar"><div><strong>${recipeSummary()}</strong><div class="muted">${run ? `本次运行 ${escapeHtml(run.id.slice(0,16))}` : '候选产物 · 不发布正式服务'}</div></div><div class="actions"><button class="btn" data-do="recipe" ${!source?'disabled':''}>配置配方</button><button class="btn primary" data-do="start" ${!recipe || !source || busy || (run&&!['COMPLETED','PARTIAL','FAILED','INTERRUPTED'].includes(run.status))?'disabled':''}>开始生产知识</button></div></div>
  <div class="workbench"><section class="workcol"><h2>原始资料</h2><div class="clause-list">${clauses.map(c=>`<button class="clause-row ${c.clause===selected?.clause?'active':''}" data-clause="${escapeHtml(c.clause)}">${escapeHtml(c.clause)}<small>${escapeHtml(c.text.slice(0,80))}${c.text.length>80?'…':''}</small></button>`).join('') || '<p class="muted">尚无原料</p>'}</div></section>
  <section class="workcol"><h2>加工过程</h2>${[['parse','解析文档'],['documents','生产条款知识'],['rules','提取业务规则'],['validation','质量验证']].map(([key,title],i)=>{const s=latest(key);return `<div class="stage ${(s?.status||'').toLowerCase()}"><span class="number">${i+1}</span><div><strong>${title}</strong><span class="status">${s?escapeHtml(label(s.status)):'等待生产'}${s?.time?' · '+escapeHtml(new Date(s.time).toLocaleTimeString()):''}</span></div></div>`;}).join('')}
  <p class="muted">${run?escapeHtml(label(run.status)):'尚未启动'}</p>${run?.error?`<div class="error-strip">${escapeHtml(errors[run.error]||run.error)}</div>`:''}</section>
  <section class="workcol"><h2>本次知识产物</h2><div class="metric"><span>条款知识</span><strong>${a?.documentClauses.length ?? '—'}</strong></div><div class="metric"><span>规则候选组</span><strong>${a?.rules.length ?? '—'}</strong></div><div class="metric"><span>抽取失败</span><strong>${run?.attempts.filter(x=>x.status==='FAILED').length ?? '—'}</strong></div>
  ${a?`<div class="notice">候选未审批、未发布。语义完整性仍需独立复核。</div>${a.rules.map(r=>`<div class="candidate-result"><strong>${escapeHtml(r.clause)} · 规则候选</strong><p class="muted">${escapeHtml(r.semantic.units.find(u=>u.kind==='CONDITION')?.quote||r.semantic.units[0]?.quote)}</p><span class="muted">受控数值子条件 ${r.projection.ir?.rules.length||0} 项 · 整条待复核</span></div>`).join('')}<button class="btn" data-do="artifacts">查看知识产物</button>`:''}
  ${run?.recipe.rulePipeline?`<p class="muted">规则抽取范围：${escapeHtml(run.recipe.selectedClauses.join('、'))}。其余条款未作规则抽取。</p>`:''}</section></div>
  ${selected?`<section class="production-inspector"><h2>${escapeHtml(selected.clause)} · 原文</h2><div class="quote">${escapeHtml(selected.text)}</div>${detail('查看原文定位',selected.anchors)}</section>`:''}
  ${run?detail('查看运行与冻结配方', {runId:run.id,recipe:run.recipe,recipeDigest:run.recipeDigest,stages:run.stages}):''}`;
}
function artifactsView() {
  const a=run?.artifact;
  const rules = a?.rules || [];
  return `<div class="pagehead"><div><h1>知识产物</h1><p class="muted">${escapeHtml(run?.title||'尚未选择生产任务')}</p></div>${a?'<button class="btn" data-do="consume">测试候选知识</button>':''}</div>
    ${a?`<div class="badge-line">${status('未审批候选')}${status(label(run.status))}</div><div class="asset-tabs">${[['documents','条款知识'],['rules','业务规则'],['quality','质量报告']].map(([id,title])=>`<button data-tab="${id}" class="${tab===id?'active':''}">${title}</button>`).join('')}</div>`:'<div class="no-content">尚无本次生产产物</div>'}
    ${a&&tab==='documents'?a.documentClauses.map(c=>`<article class="asset-row"><h3>${escapeHtml(c.clause)}</h3><div class="quote">${escapeHtml(c.text)}</div><div class="muted">来源：${escapeHtml(run.title)} · ${c.anchors.length} 处原文定位 · 适用范围尚未核定</div>${detail('来源证据',c)}</article>`).join(''):''}
    ${a&&tab==='rules'?rules.map(r=>`<article class="asset-row"><h3>${escapeHtml(r.clause)} · 业务规则候选</h3><div class="notice">${r.projection.ir?.rules.length||0} 项数值子条件完成转换；不代表整条制度满足，也不构成审批意见。</div>${r.semantic.units.map(u=>{const d=r.projection.decisions.find(x=>x.unitId===u.id);return `<div class="candidate-result">${status(d?.status || u.state)}<div class="quote">${escapeHtml(u.quote)}</div>${u.branchQuote?`<div class="muted">适用对象依据：${escapeHtml(u.branchQuote)}</div>`:''}</div>`}).join('')}${detail('查看语义、依赖关系、IR 与编译制品',r)}</article>`).join('')+(rules.length?'':'<div class="no-content">没有生成规则候选</div>'):''}
    ${a&&tab==='quality'?`<div class="notice">结构与原文引用检查不等于完整业务语义通过。独立语义金标未在此页面执行；本次产物不具备发布资格。</div><table class="source-list"><thead><tr><th>检查项</th><th>结果</th></tr></thead><tbody><tr><td>条款原文定位</td><td>${a.validation?'逐条回查通过':'验证中'}</td></tr><tr><td>用户检索测试</td><td>${a.validation?.retrievalTests.length?`${a.validation.retrievalTests.filter(t=>t.passed).length}/${a.validation.retrievalTests.length}`:'未配置，不计通过'}</td></tr><tr><td>独立语义质量</td><td>未验收</td></tr><tr><td>生产阶段规则执行</td><td>未执行，未提供业务事实</td></tr><tr><td>FAQ 编纂</td><td>未执行</td></tr></tbody></table>${run.attempts.map(t=>`<div class="asset-row"><h3>${escapeHtml(t.clause)}</h3><p>${t.status==='FAILED'?'抽取失败：'+escapeHtml(errors[t.error]||t.error):'候选已生成，需复核'}</p>${detail('模型调用记录',t)}</div>`).join('')}${detail('本次验证记录',a.validation)}`:''}
    ${run?detail('下载前核对完整运行证据',run):''}${run?'<button class="btn" data-do="export">下载本次运行 JSON</button>':''}`;
}
function consumeView() {
  const options = (run?.artifact?.rules||[]).flatMap(i=>(i.projection.ir?.rules||[]).map(r=>({clause:i.clause,id:r.id,quote:i.projection.decisions.find(d=>d.unitId===r.id)?.quote})));
  return `<div class="pagehead"><div><h1>知识消费</h1><p class="muted">${escapeHtml(run?.title||'尚无候选')} · 隔离候选测试</p></div></div><div class="notice">未接入正式知识服务或 Harness。检索返回本次原文片段，不生成无出处的答案；规则测试只判断受限数值子条件。</div>
  <div class="consume-grid"><section><h2>查询条款知识</h2><form id="search-form"><div class="field"><label for="query">问题或条款编号</label><input id="query" name="query" maxlength="300" placeholder="贷款展期有哪些期限要求？" required></div><button class="btn primary" ${!run?.artifactDigest?'disabled':''}>检索本次产物</button></form><div id="search-result">${queryResult?`<p class="muted">原文关键词检索 · ${queryResult.hits.length} 条候选证据 · 非生成式回答</p>${queryResult.hits.map(c=>`<article class="asset-row"><h3>${escapeHtml(c.clause)}</h3><div class="quote">${escapeHtml(c.text)}</div>${detail('查看引用来源',c.anchors)}</article>`).join('')}${detail('查询回执',queryResult)}`:''}</div></section>
  <section><h2>受限规则测试</h2>${options.length?`<form id="rule-form"><div class="field"><label for="rule">数值子条件</label><select id="rule">${options.map((r,i)=>`<option value="${i}">${escapeHtml(r.clause+' · '+r.quote)}</option>`).join('')}</select></div><div class="field"><label for="facts">合成业务事实（JSON）</label><textarea id="facts">{"original_months": 12, "extension_months": 6, "months": 48, "purpose_kind": "CONSUMPTION"}</textarea></div><button class="btn primary">运行隔离测试</button></form>`:'<div class="no-content">本次没有可测试的数值规则候选</div>'}
  ${testResult?`<div class="notice"><strong>${escapeHtml(label(testResult.decision))}</strong><br>整条制度：待人工复核<br>真实引擎调用：${testResult.engineCalls??'未知'} 次</div>${detail('查看本次测试回执',testResult)}`:''}</section></div>`;
}
function render() {
  if (!state) return;
  const active = run && !['COMPLETED','FAILED','PARTIAL','INTERRUPTED'].includes(run.status);
  $('#root').innerHTML=`<div class="app"><aside class="sidebar"><div class="brand"><strong>金融可信知识工厂</strong><small>知识生产工作台</small></div><nav class="nav">${[['sources','知识原料'],['production','知识生产'],['artifacts','知识产物'],['consume','知识消费']].map(([p,title])=>`<button data-page="${p}" class="${page===p?'active':''}">${title}</button>`).join('')}</nav><div class="foot-version">Web Preview V0.2<br>隔离候选 · 无发布权限<br>${escapeHtml(state.commit.slice(0,12))}${state.dirty?' + 未提交改动':''}</div></aside><main class="main"><header class="topbar"><div class="run-line"><span>工作区 / ${escapeHtml(src()?.title||'知识原料库')}</span><select class="run-select" id="run-select" aria-label="生产记录"><option value="">新生产任务</option>${state.runs.map(r=>`<option value="${r.id}" ${r.id===run?.id?'selected':''}>${escapeHtml(r.title)} · ${escapeHtml(label(r.status))} · ${r.id.slice(4,10)}</option>`).join('')}</select></div></header><div class="banner">${active?'正在执行本次知识生产':'未发布候选工作区'} · ${state.modelReady?'受管模型已配置':'受管模型未配置'} · ${state.engineReady?'Flowable 已配置':'Flowable 未配置'}</div><div class="content">${errorText?`<div role="alert" class="error-strip">${escapeHtml(errorText)}</div>`:''}${({sources:sourceView,production:workView,artifacts:artifactsView,consume:consumeView}[page])()}</div></main></div>`;
  document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{page=b.dataset.page;render()});
  document.querySelectorAll('[data-source]').forEach(b=>b.onclick=()=>{sourceId=b.dataset.source;run=null;recipe=null;page='production';render()});
  document.querySelectorAll('[data-clause]').forEach(b=>b.onclick=()=>{activeClause=b.dataset.clause;render()});
  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render()});
  document.querySelectorAll('[data-do]').forEach(b=>b.onclick=()=>dispatch(b.dataset.do));
  $('#run-select').onchange=e=>action(async()=>{queryResult=testResult=null;if(e.target.value){run=await api('/api/runs/'+e.target.value);sourceId=run.sourceId;recipe=null;localStorage.setItem('production-run',run.id);restoreResults();}else{run=null;recipe=null;localStorage.removeItem('production-run');}page='production';});
  if ($('#search-form')) $('#search-form').onsubmit=e=>{e.preventDefault();const q=$('#query').value;action(async()=>{queryResult=await api('/api/search',{runId:run.id,query:q});run=await api('/api/runs/'+run.id)})};
  if ($('#rule-form')) $('#rule-form').onsubmit=e=>{e.preventDefault();action(async()=>{const options=(run.artifact.rules||[]).flatMap(i=>(i.projection.ir?.rules||[]).map(r=>({clause:i.clause,ruleId:r.id})));const choice=options[Number($('#rule').value)];testResult=await api('/api/rule-test',{runId:run.id,...choice,inputs:JSON.parse($('#facts').value)});run=await api('/api/runs/'+run.id);})};
}
function dialog(title, body) {
  $('#modal-root').innerHTML=`<div class="modal-overlay"><section class="dialog" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}"><div class="dialog-head"><h2>${escapeHtml(title)}</h2><button class="icon-button" title="关闭" aria-label="关闭">×</button></div>${body}</section></div>`;
  $('.icon-button').onclick=()=>$('#modal-root').replaceChildren();
}
function dispatch(command) {
  if (command==='sample') return action(async()=>{const s=await api('/api/sample',{});state=await api('/api/state');sourceId=s.id;recipe=null;run=null;page='production';});
  if (command==='choose') {page='sources';render();return;}
  if (command==='artifacts'||command==='consume') {page=command;render();return;}
  if (command==='upload') {
    dialog('导入知识原料',`<form id="upload-form"><div class="field"><label for="title">原料名称</label><input id="title" required maxlength="120"></div><div class="field"><label for="file">UTF-8 HTML · 不超过 1 MB</label><input id="file" type="file" accept=".html,.htm,text/html" required></div><p class="muted">仅本地解析，不执行文件中的脚本，不读取外部资源。PDF / Word 暂未开放。</p><button class="btn primary">导入原料</button></form>`);
    $('#upload-form').onsubmit=async e=>{e.preventDefault();const file=$('#file').files[0],title=$('#title').value;if(file.size>1000000){errorText='文件超过 1 MB';$('#modal-root').replaceChildren();render();return;}const html=await file.text();$('#modal-root').replaceChildren();action(async()=>{const s=await api('/api/sources',{title,html});state=await api('/api/state');sourceId=s.id;run=null;recipe=null;page='production';});};return;
  }
  if (command==='recipe') {
    recipe ||= {sourceId, rules:false, clauses:[], tests:[],modelConsent:false};wizard=0;showWizard();return;
  }
  if (command==='start') return action(async()=>{run=await api('/api/runs',{...recipe,requestId:crypto.randomUUID()});queryResult=testResult=null;localStorage.setItem('production-run',run.id);state=await api('/api/state');});
  if (command==='export') {const blob=new Blob([JSON.stringify(run,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=run.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
}
function showWizard() {
  const s=src();
  const contents=[
    `<div class="field"><label>目标原料</label><strong>${escapeHtml(s.title)}</strong><p class="muted">${s.clauses.length} 条原文 · 当前来源版本已固定</p></div>${detail('固定来源摘要',s.id)}<div class="notice">本次产出条款知识与可选规则候选，不变更任何已发布知识。</div>`,
    `<label class="check-row"><input type="checkbox" checked disabled>文档知识 · 原生 HTML 解析、原文定位、关键词检索</label><label class="check-row"><input id="rules-check" type="checkbox" ${recipe.rules?'checked':''}>业务规则 · 语义抽取、受控转换</label><p class="muted">当前规则配方：个人贷款期限。每次最多两条；未选择的条款不进行模型抽取。</p><div id="clause-choices">${s.clauses.map(c=>`<label class="check-row"><input type="checkbox" data-pick="${escapeHtml(c.clause)}" ${recipe.clauses.includes(c.clause)?'checked':''}><span>${escapeHtml(c.clause)} · ${escapeHtml(c.text.slice(0,62))}</span></label>`).join('')}</div><p class="muted">事实关系、流程方法、案例经验：未接入。</p>`,
    `<div class="notice">原文定位与结构检查自动执行。独立语义质量仍需复核，不用模型自评替代。</div><div class="field"><label for="tests">检索测试集（JSON，最多 30 题）</label><textarea id="tests" placeholder='[{"question":"贷款展期期限","expectedClause":"第四十三条"}]'>${json(recipe.tests)}</textarea></div><div class="field"><label for="tests-file">导入测试集副本</label><input type="file" id="tests-file" accept=".json,application/json"></div><p class="muted">问题与期望条款由用户提供。AI 自动生成测试题尚未接入。</p>`,
    `<div class="field"><label>交付用途</label><strong>本地隔离候选验证</strong></div><p class="muted">不发布、不接生产 Harness，不提供共享账号权限验收。</p>${recipe.rules?`<label class="check-row"><input id="consent" type="checkbox" ${recipe.modelConsent?'checked':''}>确认所选条款为公开或已授权材料，允许发送到已配置的火山引擎 DeepSeek。</label>`:''}<p class="muted">${recipe.rules?`将调用模型 ${recipe.clauses.length} 次，不自动重试；费用未知。`:'不调用模型。'}</p>${detail('模型参数',recipe.rules?state.parameters:{modelCalls:0})}`];
  dialog('配置知识生产配方',`<div class="steps">${['目标与来源','工艺与组件','验证与测试集','交付与权限'].map((t,i)=>`<span class="${i===wizard?'active':''}">${i+1}. ${t}</span>`).join('')}</div><div id="wizard-error" role="alert"></div>${contents[wizard]}<div class="wizard-footer"><button class="btn" id="previous" ${wizard===0?'disabled':''}>上一步</button><button class="btn primary" id="next">${wizard===3?'保存配方':'下一步'}</button></div>`);
  const collect=()=>{if(wizard===1){recipe.rules=$('#rules-check').checked;recipe.clauses=recipe.rules?[...document.querySelectorAll('[data-pick]:checked')].map(e=>e.dataset.pick):[];if(recipe.rules&&(!recipe.clauses.length||recipe.clauses.length>2))throw new Error('请选择 1 至 2 条完整条款');}if(wizard===2){recipe.tests=JSON.parse($('#tests').value);if(!Array.isArray(recipe.tests)||recipe.tests.length>30)throw new Error('测试集必须是最多 30 题的数组');}if(wizard===3){recipe.modelConsent=recipe.rules?$('#consent').checked:false;if(recipe.rules&&!recipe.modelConsent)throw new Error('请先确认模型调用范围');}};
  $('#next').onclick=()=>{try{collect();if(wizard<3){wizard++;showWizard();}else{recipe.sourceId=sourceId;run=null;$('#modal-root').replaceChildren();page='production';render();}}catch(e){$('#wizard-error').textContent=e.message;}};
  $('#previous').onclick=()=>{wizard--;showWizard();};
  if($('#tests-file'))$('#tests-file').onchange=async e=>{const f=e.target.files[0];if(f&&f.size<100000)$('#tests').value=await f.text();};
}
async function poll() {
  try {
    if(run&&!['COMPLETED','PARTIAL','FAILED','INTERRUPTED'].includes(run.status)){
      run=await api('/api/runs/'+run.id);state=await api('/api/state');
      if(!$('.modal-overlay')) render();
    }
  }catch(e){errorText=e.message;render();}
  setTimeout(poll,1500);
}
async function init(){try{state=await api('/api/state');const id=localStorage.getItem('production-run');if(id&&state.runs.some(r=>r.id===id)){run=await api('/api/runs/'+id);sourceId=run.sourceId;page='production';restoreResults();}else sourceId=state.sources[0]?.id;render();poll();}catch(e){$('#root').textContent='工作区读取失败：'+e.message;}}
init();
