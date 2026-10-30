// Explicit real-model UI smoke. At most two requests, no automatic retries.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '/home/ubuntu/employee-agent-desktop/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const out=process.argv[2];
if(!out)throw new Error('Evidence directory required');
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/home/ubuntu/.cache/ms-playwright/chromium-1187/chrome-linux/chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:61352/');
  await page.getByRole('button',{name:'导入公开制度样例'}).click();
  await page.getByRole('button',{name:'配置配方'}).click();
  await page.getByRole('button',{name:'下一步',exact:true}).click();
  await page.locator('#rules-check').check();
  await page.locator('[data-pick="第八条"]').check();
  await page.locator('[data-pick="第四十三条"]').check();
  await page.getByRole('button',{name:'下一步',exact:true}).click();
  await page.locator('#tests').fill(JSON.stringify([{question:'第四十三条',expectedClause:'第四十三条'},{question:'第八条',expectedClause:'第八条'}]));
  await page.getByRole('button',{name:'下一步',exact:true}).click();
  await page.locator('#consent').check();
  await page.getByRole('button',{name:'保存配方'}).click();
  const submitted=page.waitForResponse(r=>r.url().endsWith('/api/runs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'开始生产知识',exact:true}).click();
  const job=await (await submitted).json();assert.ok(job.id);
  await page.waitForTimeout(1000);
  await page.screenshot({path:path.join(out,'running.png'),fullPage:true});
  let final;
  const deadline=Date.now()+410000;
  while(Date.now()<deadline){
   final=await page.evaluate(async id=>(await fetch('/api/runs/'+id)).json(),job.id);
   if(['COMPLETED','PARTIAL','FAILED'].includes(final.status))break;
   await page.waitForTimeout(1500);
  }
  assert.ok(['COMPLETED','PARTIAL'].includes(final.status),JSON.stringify({status:final.status,error:final.error}));
  assert.equal(final.artifact.documentClauses.length,52);
  assert.equal(final.attempts.length,2);
  assert.ok(final.attempts.every(a=>a.request.messages[1].content.length>0));
  assert.equal(final.publicationAllowed,false);
  fs.writeFileSync(path.join(out,'real-production.json'),JSON.stringify(final,null,2));
  await page.waitForTimeout(1800);
  await page.locator('[data-clause="第四十三条"]').click();
  await page.screenshot({path:path.join(out,'production-desktop.png'),fullPage:true});
  await page.getByRole('button',{name:'查看知识产物'}).click();
  await page.locator('[data-tab="rules"]').click();
  await page.screenshot({path:path.join(out,'rules.png'),fullPage:true});
  await page.getByRole('button',{name:'测试候选知识'}).click();
  await page.locator('#query').fill('第四十三条');
  await page.getByRole('button',{name:'检索本次产物'}).click();
  await page.getByText('原文关键词检索',{exact:false}).waitFor();
  if(await page.locator('#rule-form').count()){
   await page.getByRole('button',{name:'运行隔离测试'}).click();
   await page.getByText('整条制度：待人工复核',{exact:false}).waitFor({timeout:60000});
  }
  await page.screenshot({path:path.join(out,'consumption.png'),fullPage:true});
  await page.reload();
  await page.getByRole('heading',{name:'知识生产车间'}).waitFor();
  assert.equal(await page.locator('#run-select').inputValue(),job.id);
  for(const width of [390,320]){
   await page.setViewportSize({width,height:844});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(out,'production-'+width+'.png'),fullPage:true});
  }
  await page.setViewportSize({width:1366,height:900});
  await page.locator('[data-page="sources"]').click();
  await page.getByRole('button',{name:'上传 HTML',exact:true}).click();
  await page.locator('#title').fill('上传样例 · 客服制度');
  await page.locator('#file').setInputFiles({name:'customer-policy.html',mimeType:'text/html',buffer:Buffer.from('<html><body><p>第一条 客户咨询应引用已公布的服务条款。</p><p>第二条 无法确认的信息交由人工核实。</p><script>window.XSS=1</script></body></html>')});
  await page.getByRole('button',{name:'导入原料',exact:true}).click();
  await page.getByRole('heading',{name:'知识生产车间'}).waitFor();
  await page.getByRole('button',{name:'配置配方'}).click();
  for(let i=0;i<3;i++)await page.getByRole('button',{name:'下一步',exact:true}).click();
  await page.getByRole('button',{name:'保存配方'}).click();
  const second=page.waitForResponse(r=>r.url().endsWith('/api/runs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'开始生产知识'}).click();
  const upload=await (await second).json();
  await page.waitForTimeout(1800);
  const uploadResult=await page.evaluate(async id=>(await fetch('/api/runs/'+id)).json(),upload.id);
  assert.equal(uploadResult.status,'COMPLETED');assert.equal(uploadResult.artifact.documentClauses.length,2);
  assert.equal(uploadResult.attempts.length,0);assert.equal(await page.evaluate(()=>window.XSS),undefined);
  assert.notEqual(uploadResult.sourceId,final.sourceId);assert.notEqual(uploadResult.id,final.id);
  fs.writeFileSync(path.join(out,'uploaded-document-production.json'),JSON.stringify(uploadResult,null,2));
  final=await page.evaluate(async id=>(await fetch('/api/runs/'+id)).json(),job.id);
  fs.writeFileSync(path.join(out,'real-production.json'),JSON.stringify(final,null,2));
  assert.equal(errors.length,0,errors.join('\n'));
  const result={realRunId:job.id,uploadRunId:upload.id,modelCalls:final.attempts.length,
    generatedRuleGroups:final.artifact.rules.length,failedExtractions:final.attempts.filter(a=>a.status==='FAILED').length,
    documentClauses:52,uploadClauses:2,historyRefresh:true,sourceIsolation:true,mobileWidths:[390,320],
    publicationAllowed:false,pageErrors:errors,cost:null};
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
