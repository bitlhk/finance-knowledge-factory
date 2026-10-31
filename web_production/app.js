'use strict';
const $ = s => document.querySelector(s);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const json = x => escapeHtml(JSON.stringify(x, null, 2));
let state, page = 'production', sourceId, run, activeClause, tab = 'documents', errorText = '', busy = false;
let recipe = null, wizardDraft = null, wizard = 0, queryResult = null, testResult = null;
const labels = {QUEUED:'排队中', RUNNING:'加工中', COMPLETED:'加工结束', PARTIAL:'部分完成',
  FAILED:'失败，记录已保留', INTERRUPTED:'执行中断，未自动重试', NOT_SELECTED:'未选择',
  REVIEW_REQUIRED:'待人工复核', MET:'数值子条件满足', NOT_MET:'数值子条件不满足',
  INVALID_INPUT:'输入不合法', UNKNOWN:'无法确认', NOT_APPLICABLE:'不适用',
  VERIFIED_NUMERIC:'受控转换已完成', UNSUPPORTED:'当前工艺不支持', UNVERIFIABLE:'待确认转换依据',
  MANUAL:'需人工确认', EXTERNAL:'缺少外部依据', PROPOSED_NUMERIC:'数值条件候选'};
const label = x => labels[x] || x;
const m2Mode = () => Boolean(state?.m2);
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
  try { await fn(); } catch (e) { errorText = e.message; if($('#modal-error'))$('#modal-error').textContent=e.message; }
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
function sandboxView() {
  if (m2Mode()) return window.m2.sandbox();
  const options = (run?.artifact?.rules||[]).flatMap(i=>(i.projection.ir?.rules||[]).map(r=>({clause:i.clause,id:r.id,quote:i.projection.decisions.find(d=>d.unitId===r.id)?.quote})));
  return `<div class="pagehead"><div><h1>候选隔离测试</h1><p class="muted">${escapeHtml(run?.title||'尚无候选')} · 隔离候选测试</p></div></div><div class="notice">未接入正式知识服务或 Harness。检索返回本次原文片段，不生成无出处的答案；规则测试只判断受限数值子条件。</div>
  <div class="consume-grid"><section><h2>查询条款知识</h2><form id="search-form"><div class="field"><label for="query">问题或条款编号</label><input id="query" name="query" maxlength="300" value="${escapeHtml(queryResult?.query||'')}" placeholder="贷款展期有哪些期限要求？" required></div><button class="btn primary" ${!run?.artifactDigest?'disabled':''}>检索本次产物</button></form><div id="search-result">${queryResult?`<p class="muted">原文关键词检索 · ${queryResult.hits.length} 条候选证据 · 非生成式回答</p>${queryResult.hits.map(c=>`<article class="asset-row"><h3>${escapeHtml(c.clause)}</h3><div class="quote">${escapeHtml(c.text)}</div>${detail('查看引用来源',c.anchors)}</article>`).join('')}${detail('查询回执',queryResult)}`:''}</div></section>
  <section><h2>受限规则测试</h2>${options.length?`<form id="rule-form"><div class="field"><label for="rule">数值子条件</label><select id="rule">${options.map((r,i)=>`<option value="${i}" ${testResult?.ruleId===r.id&&testResult?.clause===r.clause?'selected':''}>${escapeHtml(r.clause+' · '+r.quote)}</option>`).join('')}</select></div><div class="field"><label for="facts">合成业务事实（JSON）</label><textarea id="facts">${json(testResult?.inputs||{original_months:12,extension_months:6,months:48,purpose_kind:'CONSUMPTION'})}</textarea></div><button class="btn primary">运行隔离测试</button></form>`:'<div class="no-content">本次没有可测试的数值规则候选</div>'}
  ${testResult?`<div class="notice"><strong>${escapeHtml(label(testResult.decision))}</strong><br>整条制度：待人工复核<br>真实引擎调用：${testResult.engineCalls??'未知'} 次</div>${detail('查看本次测试回执',testResult)}`:''}</section></div>`;
}
function bindTests() {
  if ($('#search-form')) $('#search-form').onsubmit=e=>{e.preventDefault();const q=$('#query').value;action(async()=>{if(m2Mode())queryResult=null;try{queryResult=await api('/api/search',{runId:run.id,query:q});run=await api('/api/runs/'+run.id);}finally{showSandbox()}})};
  if ($('#rule-form')) $('#rule-form').onsubmit=e=>{e.preventDefault();const facts=$('#facts').value, index=Number($('#rule').value);action(async()=>{const options=(run.artifact.rules||[]).flatMap(i=>(i.projection.ir?.rules||[]).map(r=>({clause:i.clause,ruleId:r.id})));testResult=await api('/api/rule-test',{runId:run.id,...options[index],inputs:JSON.parse(facts)});run=await api('/api/runs/'+run.id);showSandbox()})};
}
function showSandbox(){dialog(m2Mode()?'隔离知识服务查询':'候选知识隔离测试',sandboxView());bindTests();}
function render() {
  if (!state) return;
  const pages=[['sources','知识原料'],['production','知识生产'],['artifacts','知识产物'],['consume','知识消费']];
  $('#root').innerHTML=`<div class="app"><aside class="sidebar"><div class="brand"><div class="brand-logo">知</div><div><div class="brand-title">金融可信知识工厂</div><div class="brand-sub">KNOWLEDGE FACTORY · V1.5</div></div></div><div class="navlabel">知识全生命周期</div><nav class="nav">${pages.map(([p,title],i)=>`<button data-page="${p}" class="${page===p?'active':''}"><span class="navno">0${i+1}</span>${title}</button>`).join('')}</nav><div class="sidebottom">隔离知识生产 · 无发布权限<br>Web Preview V0.2<br>${E(state.commit.slice(0,12))}${state.dirty?' + 未提交改动':''}</div></aside><main class="page"><header class="topbar"><div class="crumb">金融 AI / 知识工程 / <b>${pages.find(p=>p[0]===page)?.[1]}</b></div><div class="topcontrols"><span class="small textmuted">当前试产产品</span><select class="selector" id="product-select" aria-label="当前知识产品">${state.sources.length?state.sources.map(s=>`<option value="${s.id}" ${s.id===sourceId?'selected':''}>${E(s.title)}</option>`).join(''):'<option>尚无产品</option>'}</select><span class="versiontag">真实加工 · 未发布</span></div></header><div class="content">${errorText?`<div role="alert" class="error-strip">${E(errorText)}</div>`:''}${({sources:sourceView,production:workView,artifacts:artifactsView,consume:consumeView}[page])()}</div></main></div>`;
  document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{page=b.dataset.page;if(page==='production')workshopOpen=false;render()});
  if(m2Mode()){
    $('.sidebottom').textContent='隔离测试工作区 · M2 文档知识 · '+state.commit.slice(0,12)+(state.dirty?' + 未提交改动':'');
    $('.versiontag').textContent=run?.release?.state==='ISOLATED_PUBLISHED'?'隔离快照已绑定':'真实加工 · 候选';
  }
  document.querySelectorAll('[data-source]').forEach(b=>b.onclick=()=>action(()=>openProduct(b.dataset.source)));
  document.querySelectorAll('[data-do]').forEach(b=>b.onclick=()=>dispatch(b.dataset.do));
  if($('#run-select'))$('#run-select').onchange=e=>action(async()=>{if(e.target.value)await openProduct(sourceId,e.target.value);else{run=null;recipe=null;queryResult=testResult=null;localStorage.removeItem('production-run');}});
  bindWorkshop();
}
function dialog(title, body) {
  $('#modal-root').innerHTML=`<div class="modalback modal-overlay"><section class="modal dialog" role="dialog" aria-modal="true" aria-label="${E(title)}"><div class="modalhead"><h2>${E(title)}</h2><button class="close icon-button" title="关闭" aria-label="关闭">×</button></div><div class="modalbody"><div id="modal-error" role="alert"></div>${body}</div></section></div>`;
  $('.icon-button').onclick=()=>$('#modal-root').replaceChildren();
}
function dispatch(command) {
  if(m2Mode()&&['approve-document','publish-document'].includes(command))return window.m2.release(command);
  if(command==='catalog'){workshopOpen=false;page='production';render();return;}
  if(command==='workshop'){workshopOpen=true;page='production';render();return;}
  if(command==='checks'){$('#production-checks')?.scrollIntoView({behavior:'smooth'});return;}
  if(command==='sandbox'){showSandbox();return;}
  if(command==='crafts'){craftDialog();return;}
  if(command==='new-product'){dialog('新建知识产品试产','<div class="hint">本轮以一份固定 HTML 原料组织试产；多来源产品配置尚未接入。</div><div class="actions"><button class="btn secondary" id="use-library">从原料库选择</button><button class="btn" id="use-upload">上传新资料</button></div>');$('#use-library').onclick=()=>{$('#modal-root').replaceChildren();page='sources';render()};$('#use-upload').onclick=()=>dispatch('upload');return;}
  if(command==='tests'||command==='components'){dispatch('recipe');wizard=command==='tests'?2:1;showWizard();return;}

  if (command==='sample') return action(async()=>{const s=await api('/api/sample',{});state=await api('/api/state');sourceId=s.id;recipe=null;run=null;queryResult=testResult=null;workshopOpen=true;localStorage.removeItem('production-run');page='production';});
  if (command==='choose') {page='sources';render();return;}
  if (command==='artifacts'||command==='consume') {page=command;render();return;}
  if (command==='upload') {
    dialog('导入知识原料',`<form id="upload-form"><div class="field"><label for="title">原料名称</label><input id="title" required maxlength="120"></div><div class="field"><label for="file">UTF-8 HTML · 不超过 1 MB</label><input id="file" type="file" accept=".html,.htm,text/html" required></div><p class="muted">仅本地解析，不执行文件中的脚本，不读取外部资源。PDF / Word 暂未开放。</p><button class="btn primary">导入原料</button></form>`);
    $('#upload-form').onsubmit=async e=>{e.preventDefault();const file=$('#file').files[0],title=$('#title').value;if(file.size>1000000){errorText='文件超过 1 MB';$('#modal-root').replaceChildren();render();return;}const html=await file.text();$('#modal-root').replaceChildren();action(async()=>{const s=await api('/api/sources',{title,html});state=await api('/api/state');sourceId=s.id;run=null;recipe=null;queryResult=testResult=null;workshopOpen=true;localStorage.removeItem('production-run');page='production';});};return;
  }
  if (command==='recipe') {
    wizardDraft = structuredClone(recipe || (run ? {sourceId, rules:Boolean(run.recipe.rulePipeline), clauses:[...run.recipe.selectedClauses], tests:run.recipe.tests, modelConsent:false} : {sourceId,rules:false,clauses:[],tests:[],modelConsent:false}));wizard=0;showWizard();return;
  }
  if (command==='start') return action(async()=>{run=await api('/api/runs',{...recipe,requestId:crypto.randomUUID()});queryResult=testResult=null;localStorage.setItem('production-run',run.id);state=await api('/api/state');});
  if (command==='export') {const blob=new Blob([JSON.stringify(run,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=run.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
}
function showWizard() {
  const s=src(), d=wizardDraft;
  const components=()=>`<div class="v14-config"><div class="v14-configtitle">公共接入组件</div><div class="wizardgrid"><div class="field"><label>解析与原文定位</label><select disabled><option>原生 HTML DOM · v0.1</option></select></div><div class="field"><label>来源版本</label><input readonly value="固定内容摘要 · 不跟随最新上传"></div></div></div><div class="v14-config"><div class="v14-configtitle">文档知识组件</div><p>条款拆分与锚点验证 → 本地关键词检索</p><div class="hint">RAGFlow 服务、FAQ 编纂、PDF / Word 未接入本页面。</div></div>${d.rules?`<div class="v14-config"><div class="v14-configtitle">业务规则组件</div><div class="wizardgrid"><div class="field"><label>语义识别</label><select disabled><option>火山引擎 DeepSeek · 固定参数</option></select></div><div class="field"><label>规则转换与执行</label><select disabled><option>受控转换 / Flowable 隔离测试</option></select></div></div><p class="small textmuted">个人贷款期限字段词表 · 每次选择 1 至 2 条完整条款</p><div id="clause-choices">${s.clauses.map(c=>`<label class="checkbox"><input type="checkbox" data-pick="${E(c.clause)}" ${d.clauses.includes(c.clause)?'checked':''}><span>${E(c.clause)} · ${E(c.text.slice(0,62))}</span></label>`).join('')}</div></div>`:''}`;
  const rows=()=>d.tests.map((t,i)=>`<div class="test-row"><div class="field"><label>问题 ${i+1}</label><input data-question="${i}" maxlength="300" value="${E(t.question)}"></div><div class="field"><label>期望条款</label><select data-expected="${i}"><option value="">选择条款</option>${s.clauses.map(c=>`<option ${t.expectedClause===c.clause?'selected':''}>${E(c.clause)}</option>`).join('')}</select></div><button class="close" title="删除题目" aria-label="删除题目 ${i+1}" data-remove="${i}">×</button></div>`).join('');
  const contents=[
    `<div class="wizardgrid"><div class="field"><label>生产目标</label><select disabled><option>条款知识与可选业务规则候选</option></select></div><div class="field"><label>固定来源版本</label><input readonly value="${E(s.title)}"></div></div><div class="v14-choice"><div><strong>${E(s.title)}</strong><p class="small textmuted">HTML · ${s.clauses.length} 条原文</p></div>${badge('已固定版本')}</div>${detail('来源摘要',s.id)}<div class="hint">本轮为单来源试产。修改配方创建新任务，不会改写已有产物。</div>`,
    `<div class="checkgrid"><label class="checkline"><input type="checkbox" checked disabled><span><b>文档知识</b>原文定位与条款知识</span></label><label class="checkline"><input id="rules-check" type="checkbox" ${d.rules?'checked':''}><span><b>业务规则</b>语义识别与受控转换</span></label>${['事实关系','流程方法','案例经验'].map(t=>`<label class="checkline"><input type="checkbox" disabled><span><b>${t}</b>未接入，不能运行</span></label>`).join('')}</div><div id="component-config">${components()}</div>`,
    `<div class="v14-testentry"><div><b>检索测试集</b><p class="small textmuted">问题与期望条款由用户提供；不作为独立语义验收。</p></div><button class="btn secondary sm" id="add-test">＋ 新增问题</button></div><div id="test-rows">${rows()}</div><div class="field"><label for="tests-file">导入 JSON 测试集副本（最多 30 题）</label><input type="file" id="tests-file" accept=".json,application/json"></div><button class="btn secondary" disabled title="AI 生成测试集尚未接入">AI 生成测试题</button><div class="hint">原文定位与结构检查自动执行。独立语义质量仍需复核。</div>`,
    `<div class="wizardgrid"><div class="field"><label>交付用途</label><select disabled><option>本地隔离候选验证</option></select></div><div class="field"><label>版本策略</label><select disabled><option>固定本次来源与配方，不发布</option></select></div><div class="field"><label>允许消费的角色</label><input disabled value="未接入业务 IAM"></div><div class="field"><label>历史回放的角色</label><input disabled value="未接入业务 IAM"></div></div><div class="hint">权限设置未开放；候选不能供正式服务或生产 Harness 使用。</div>${d.rules?`<label class="checkbox"><input id="consent" type="checkbox" ${d.modelConsent?'checked':''}>确认所选条款为公开或已授权材料，允许发送到已配置的火山引擎 DeepSeek。</label>`:''}<p>${d.rules?'将调用模型 '+d.clauses.length+' 次，不自动重试；费用未知。':'本次不调用模型。'}</p>${detail('执行参数',d.rules?state.parameters:{modelCalls:0})}`
  ];
  dialog('配置知识生产配方',`<div class="wizardsteps">${['目标与来源','工艺与组件','验证与测试集','交付与权限'].map((t,i)=>`<div class="wstep ${i===wizard?'on':''}">${i+1}. ${t}</div>`).join('')}</div><div id="wizard-error" role="alert"></div>${contents[wizard]}<div class="modalfoot"><button class="btn secondary" id="previous" ${wizard===0?'disabled':''}>上一步</button><button class="btn" id="next">${wizard===3?'保存配方':'下一步'}</button></div>`);
  if(m2Mode())window.m2.wizard(wizard);
  function readTests(){document.querySelectorAll('[data-question]').forEach(el=>d.tests[Number(el.dataset.question)].question=el.value);document.querySelectorAll('[data-expected]').forEach(el=>d.tests[Number(el.dataset.expected)].expectedClause=el.value);}
  function collect(validate=true){
    if(wizard===1){d.rules=$('#rules-check').checked;d.clauses=d.rules?[...document.querySelectorAll('[data-pick]:checked')].map(el=>el.dataset.pick):[];if(validate&&d.rules&&(!d.clauses.length||d.clauses.length>2))throw Error('请选择 1 至 2 条完整条款');}
    if(wizard===2){readTests();if(validate&&m2Mode()&&!d.tests.length)throw Error('隔离发布至少需要一条检索测试题');if(validate&&d.tests.some(t=>!t.question.trim()||!s.clauses.some(c=>c.clause===t.expectedClause)))throw Error('每题需要问题和当前来源中的期望条款');}
    if(wizard===3){d.modelConsent=d.rules?$('#consent').checked:false;if(validate&&d.rules&&!d.modelConsent)throw Error('请先确认模型调用范围');}
  }
  $('#next').onclick=()=>{try{collect();if(wizard<3){wizard++;showWizard();}else{recipe=structuredClone(d);recipe.sourceId=sourceId;run=null;queryResult=testResult=null;localStorage.removeItem('production-run');workshopOpen=true;$('#modal-root').replaceChildren();page='production';render();}}catch(e){$('#wizard-error').textContent=e.message;}};
  $('#previous').onclick=()=>{collect(false);wizard--;showWizard();};
  if($('#rules-check'))$('#rules-check').onchange=()=>{collect(false);showWizard()};
  if($('#add-test'))$('#add-test').onclick=()=>{readTests();if(d.tests.length>=30){$('#wizard-error').textContent='最多 30 题';return;}d.tests.push({question:'',expectedClause:''});showWizard()};
  document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{readTests();d.tests.splice(Number(b.dataset.remove),1);showWizard()});
  if($('#tests-file'))$('#tests-file').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>100000)throw Error('测试集文件过大');const t=JSON.parse(await f.text());if(!Array.isArray(t)||t.length>30||t.some(x=>!x||typeof x.question!=='string'||typeof x.expectedClause!=='string'||Object.keys(x).sort().join(',')!=='expectedClause,question'))throw Error('需要 question / expectedClause 对象数组，最多 30 题');d.tests=t;showWizard()}catch(err){$('#wizard-error').textContent=err.message}};
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
async function init(){try{state=await api('/api/state');const id=localStorage.getItem('production-run');if(id&&state.runs.some(r=>r.id===id)){run=await api('/api/runs/'+id);sourceId=run.sourceId;page='production';workshopOpen=true;restoreResults();}else sourceId=state.sources[0]?.id;render();poll();}catch(e){$('#root').textContent='工作区读取失败：'+e.message;}}
