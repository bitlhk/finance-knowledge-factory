'use strict';
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const raw = x => `<pre class="raw mono">${esc(typeof x === 'string' ? x : JSON.stringify(x,null,2))}</pre>`;
const button = (label, action, value, cls='btn secondary') => `<button class="${cls}" data-action="${action}" data-value="${esc(value)}">${esc(label)}</button>`;
let data, page='production', attempt='P43-1', stage='coverage', selectedAnchor=0, wizard=null, receipt='candidate', missingQuote='';
const pages = {sources:'知识原料',production:'知识生产',artifacts:'知识产物',consumption:'知识消费'};
const stages = {source:'原文与锚点',coverage:'语义覆盖',projection:'受控转换',assessment:'冻结验证',execution:'执行回执'};
const status = x => ({REVIEW_REQUIRED:'待复核',SEMANTIC_ERROR:'语义错误',NOT_APPLICABLE:'不适用',UNKNOWN:'未知',INVALID_INPUT:'输入无效',MET:'数值条件满足',NOT_MET:'数值条件不满足',INPUT_SCOPE_GUARD:'前置守卫'}[x] || x);
const bundle = () => data.bundles[attempt];
const archive = () => data.files[`archive/${attempt}-bundle.json`];
const selectAttempt = () => `<label>固定实验 <select id="attempt" class="selector">${Object.keys(data.bundles).map(k=>`<option ${attempt===k?'selected':''}>${k}</option>`).join('')}</select></label>`;
function anchors() {
 return bundle().parts.bridge.mappings.map((m,i)=>`<button class="anchor-button" data-action="anchor" data-value="${i}" aria-pressed="${i===selectedAnchor}">${esc(m.clause)} · 原始锚点 ${i+1}<br><span class="small digest">${esc(m.anchorId.slice(0,16))}</span></button>`).join('');
}
function sourceView() {
 const p=bundle().parts,m=p.bridge.mappings[selectedAnchor];
 return `<div class="sources-layout"><section><h3>条款原文</h3><div class="source-quote">${esc(p.source.content)}</div>${anchors()}<h3>选中来源</h3>${m?`<p class="source-quote selected-quote">${esc(m.anchor.quote)}</p>${raw(m.anchor.locator)}`:`<div role="alert" class="risk">该模型引用未精确匹配冻结原文，不能确认来源锚点。${raw(missingQuote)}</div>`}<p>定位空间：原始 HTML DOM；派生行号不代表页码。</p></section><section><h3>来源版本</h3>${raw({sourceBytesDigest:data.sourceSha256,anchorId:m?.anchorId??null,quoteDigest:m?.anchor.quoteDigest??null})}<details><summary>完整原文（纯文本）</summary><pre class="raw full-source">${esc(data.originalText)}</pre></details></section></div>`;
}
function receipts() {
 if(attempt!=='P43-1')receipt='candidate';
 const record=receipt==='candidate'?archive():data.files['addendum/archive/engine-response.json'];
 const rows=record.results||[];
 return `<label>证据类型 <select id="receipt" class="selector receipt-select"><option value="candidate" ${receipt==='candidate'?'selected':''}>原候选验证（不改旧结果）</option><option value="numeric" ${receipt==='numeric'?'selected':''} ${attempt!=='P43-1'?'disabled':''}>P43 独立数值诊断（不是候选放行）</option></select></label>${receipt==='numeric'?'<p class="warn">独立诊断制品。通过不代表完整条款正确，也不覆盖原候选失败。</p>':''}<h3>实际归档回执</h3>${rows.length?`<p>原断言通过 ${rows.filter(r=>r.passed).length}/${rows.length} · 实际引擎执行 ${rows.filter(r=>r.executor?.startsWith('FLOWABLE')).length} 次</p><table class="table"><thead><tr><th>案例</th><th>预期 / 实际</th><th>执行者</th><th>原断言</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.id)}</td><td>${esc(status(r.expected))}<br>${esc(status(r.actual))}</td><td>${esc(status(r.executor))}</td><td>${r.passed?'通过':'失败'}</td></tr>`).join('')}</tbody></table>`:'<p class="empty">本候选未产生可执行案例。无引擎执行证据，不等于验证通过。</p>'}<details open><summary>完整回执及运行标识</summary>${raw(record)}</details><details><summary>执行前快照（不是最终结果）</summary>${raw(bundle().parts.execution)}</details>`;
}
function detail() {
 const p=bundle().parts;
 if(stage==='source') return sourceView();
 if(stage==='execution') return receipts();
 if(stage==='coverage') return `<div class="inspectthree"><section class="inspectpane"><b>模型识别的语义单元</b><ul class="audit-list">${p.coverage.units.map(u=>`<li><strong>${esc(u.id)} · ${esc(u.kind)} · ${esc(u.state)}</strong><p>${esc(u.quote)}</p>${button('查看原文依据','quote',u.quote,'btn secondary sm')}</li>`).join('')}</ul></section><section class="inspectpane"><b>语义关联与原始回答</b>${raw(p.coverage.relations)}<details><summary>实际模型返回正文</summary>${raw(p.response.choices[0].message.content)}</details></section></div>`;
 if(stage==='assessment') return `<h3>冻结口径结果 · ${esc(status(p.assessment.status))}</h3>${raw(p.assessment)}<details><summary>事后附加复核（不替换冻结评分）</summary>${raw(data.files['addendum/review.json'])}</details><details><summary>当次金标与来源</summary>${raw(p.gold)}</details>`;
 return `<h3>受控转换候选 · 未批准</h3>${raw(p.projection)}<details><summary>编译制品及证据绑定</summary>${raw({compiled:p.compiled,binding:p.binding})}</details>`;
}
function workshop() {
 const p=bundle().parts;
 return `<div class="heading"><div><div class="eyebrow">KNOWLEDGE PRODUCTION</div><h1 class="h1">个人贷款制度 · 知识生产车间</h1><p class="sub">真实历史证据 · 未验收候选 · 不具备发布权限</p></div>${button('查看冻结配方','wizard','0')}</div><div class="workbench"><section class="workcol"><div class="colhead"><b>原始资料</b><button disabled class="btn secondary sm" title="历史证据预览不接收新文件">导入</button></div><button class="sourcetile on" data-action="stage" data-value="source"><b>《个人贷款管理办法》</b><small>固定来源 · HTML 原件</small></button>${anchors()}<p class="small digest">SHA-256 ${esc(data.sourceSha256)}</p></section><section class="workcol"><div class="colhead"><b>知识加工过程</b></div><div class="processintro"><b>固定原文与专业配方</b>只读回看，不触发生产任务</div><div class="procdown">↓</div><div class="lane"><div class="lanetitle"><strong>文档知识</strong><span>原文定位</span></div>${button('原文与锚点','stage','source',`workstep ${stage==='source'?'on':''}`)}</div><div class="lane"><div class="lanetitle"><strong>业务规则</strong><span>受限安全子集</span></div><div class="steprow">${Object.entries(stages).filter(([k])=>k!=='source').map(([k,v])=>button(v,'stage',k,`workstep ${stage===k?'on':''}`)).join('<span class="stepsep">→</span>')}</div></div><p class="small">事实关系、流程方法、案例经验：规划工艺，本预览无执行证据。</p></section><section class="workcol"><div class="colhead"><b>知识产物</b><span class="badge gold">待验收</span></div>${button('条款与来源锚点','stage','source','outputtile')}${button('语义覆盖与依赖','stage','coverage','outputtile')}${button('Rule IR 候选与编译制品','stage','projection','outputtile')}<div class="warn">冻结验证：${esc(status(p.assessment.status))}<br>正式 Manifest：无<br>生产环境发布：禁止</div></section></div><section class="inspect"><div class="inspecttop"><h3>${stages[stage]}</h3><span class="badge">历史记录 · ${attempt}</span></div><div class="pad">${detail()}</div></section>`;
}
function artifacts() {
 return `<h1 class="h1">知识产物</h1><p class="sub">候选资产，不是正式发布目录。所有历史失败保持原样。</p><table class="table"><thead><tr><th>候选</th><th>冻结验证</th><th>摘要</th><th>发布</th></tr></thead><tbody>${Object.entries(data.bundles).map(([id,b])=>`<tr><td>${button(id,'artifact',id,'btn secondary sm')}</td><td>${esc(status(b.parts.assessment.status))}</td><td class="digest">${data.fileDigests[`attempts/${id}-bundle.json`]}</td><td>未批准</td></tr>`).join('')}</tbody></table><h3>证据来源</h3>${raw({evidenceCommit:data.evidenceCommit,prototypeSha256:data.prototypeSha256,indexSha256:data.indexSha256})}<a class="snapshot-link" href="/api/snapshot" download="historical-evidence.json">下载已核验快照</a>`;
}
function render() {
 document.getElementById('root').innerHTML=`<div class="app"><aside class="sidebar"><div class="brand"><div class="brand-logo">知</div><div class="brand-title">金融可信知识工厂<div class="brand-sub">WEB PREVIEW V0.1</div></div></div><nav class="nav">${Object.entries(pages).map(([k,v],i)=>`<button data-action="page" data-value="${k}" class="${page===k?'active':''}"><span class="navno">0${i+1}</span>${v}</button>`).join('')}</nav><div class="sidebottom">V1.5 产品基线<br>M1 固定证据 · 只读</div></aside><main class="page"><header class="topbar"><div class="crumb">知识工厂 / <b>${pages[page]}</b></div><div class="topcontrols">${selectAttempt()}<span class="versiontag">证据 ${data.evidenceCommit.slice(0,8)}</span></div></header><div class="banner">真实历史证据；当前无实时执行、无模拟成功、无已发布知识服务。</div><div class="content">${page==='production'?workshop():page==='sources'?'<h1 class="h1">知识原料</h1>'+sourceView():page==='artifacts'?artifacts():`<h1 class="h1">知识消费</h1><div class="warn">正式知识服务与 Harness 接入：本证据包未验收。以下仅为保存的执行回执，不是当前服务调用。</div><h3>历史执行记录</h3>${receipts()}`}</div></main></div>`;
 renderWizard();
}
function renderWizard() {
 const target=document.getElementById('modal-root');
 if(wizard===null){target.innerHTML='';return;}
 const p=bundle().parts;
 const content=[{source:p.source,sourceDigest:data.sourceSha256,scope:'限定条款历史探针'}, {recipe:p.recipe,requestParameters:Object.fromEntries(Object.entries(p.request).filter(([k])=>k!=='messages'))}, {gold:p.gold,validation:p.assessment}, {publicationAllowed:false,manifest:null,serviceRoles:'未接入真实 IAM',historyAccess:'仅本机只读预览'}];
 target.innerHTML=`<div class="modalback"><section role="dialog" aria-modal="true" aria-label="冻结配方" class="modal"><div class="modalhead"><h2>冻结配方 · 只读</h2>${button('关闭','close','','btn secondary sm')}</div><div class="modalbody"><div class="wizardsteps">${['目标与来源','工艺与组件','测试与验证','交付与权限'].map((v,i)=>button(v,'wizard',i,`wstep ${i===wizard?'on':''}`)).join('')}</div>${raw(content[wizard])}</div><div class="modalfoot"><span>修改草稿不会改变本次历史记录</span><button disabled class="btn">保存 / 发布不可用</button></div></section></div>`;
}
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-action]');if(!b||!data)return;
 const {action,value}=b.dataset;
 if(action==='page')page=value;
 if(action==='stage'){stage=value;page='production';}
 if(action==='anchor'){selectedAnchor=Number(value);stage='source';}
 if(action==='artifact'){attempt=value;selectedAnchor=0;page='production';stage='projection';}
 if(action==='quote'){selectedAnchor=bundle().parts.bridge.mappings.findIndex(m=>m.anchor.quote.includes(value));missingQuote=value;stage='source';}
 if(action==='wizard')wizard=Number(value);
 if(action==='close')wizard=null;
 render();
});
document.addEventListener('change',e=>{if(e.target.id==='attempt'){attempt=e.target.value;selectedAnchor=0;}if(e.target.id==='receipt')receipt=e.target.value;render();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){wizard=null;renderWizard();}});
fetch('/api/snapshot').then(r=>{if(!r.ok)throw Error('unavailable');return r.json();}).then(x=>{data=x;render();}).catch(()=>{document.getElementById('root').innerHTML='<div class="error" role="alert"><h1>证据不可用</h1><p>固定证据缺失、摘要变化或加载失败。已阻断预览，未使用模拟数据回退。</p></div>';});
