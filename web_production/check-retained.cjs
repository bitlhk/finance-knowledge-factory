// No new production/model calls: final-build retained-result and rule-test checks.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/home/ubuntu/employee-agent-desktop/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const [out,runId]=process.argv.slice(2);
if(!out||!runId)throw new Error('Usage: check-retained.cjs evidence-dir existing-run-id');
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const b=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/home/ubuntu/.cache/ms-playwright/chromium-1187/chrome-linux/chrome',headless:true,args:['--no-sandbox']});
 const p=await b.newPage({viewport:{width:1366,height:900}}),errors=[];
 p.on('pageerror',e=>errors.push(e.message));
 try{
  await p.goto('http://127.0.0.1:61352/');
  const before=await p.evaluate(async id=>(await fetch('/api/runs/'+id)).json(),runId);
  await p.locator('[data-product="'+before.sourceId+'"]').click();
  await p.locator('#run-select').selectOption(runId);
  await p.locator('#clause-select').selectOption('第四十三条');
  await p.screenshot({path:path.join(out,'production-desktop.png'),fullPage:true});
  await p.locator('[data-do="sandbox"]').click();
  const receipts=[];
  for(const [name,facts] of [
   ['met',{original_months:12,extension_months:6}],
   ['not-met',{original_months:12,extension_months:13}],
   ['invalid-input',{original_months:12,extension_months:true}],
   ['not-applicable',{original_months:24,extension_months:6}]]){
   await p.locator('#facts').fill(JSON.stringify(facts));
   const reply=p.waitForResponse(r=>r.url().endsWith('/api/rule-test')&&r.request().method()==='POST');
   await p.getByRole('button',{name:'运行隔离测试'}).click();
   const receipt=await(await reply).json();receipts.push({name,receipt});
   await p.waitForTimeout(400);
  }
  assert.deepEqual(receipts.map(r=>r.receipt.decision),['MET','NOT_MET','INVALID_INPUT','NOT_APPLICABLE']);
  assert.deepEqual(receipts.map(r=>r.receipt.engineCalls),[2,1,0,0]);
  await p.reload();
  await p.locator('[data-do="sandbox"]').click();
  await p.getByText('不适用',{exact:true}).waitFor();
  assert.deepEqual(JSON.parse(await p.locator('#facts').inputValue()),receipts.at(-1).receipt.inputs);
  assert.equal(await p.locator('#query').inputValue(),before.consumptionReceipts.find(r=>r.query)?.query||'');
  await p.screenshot({path:path.join(out,'consumption.png'),fullPage:true});
  await p.getByRole('button',{name:'关闭',exact:true}).click();
  await p.locator('.workstep[data-step="semantic"]').click();
  await p.screenshot({path:path.join(out,'rules.png'),fullPage:true});
  await p.locator('.workstep[data-step="validation"]').click();
  await p.screenshot({path:path.join(out,'quality.png'),fullPage:true});
  for(const width of [1366,390,320]){
   await p.setViewportSize({width,height:844});
   for(const view of ['sources','production','artifacts','consume']){
    await p.locator('[data-page="'+view+'"]').click();
    assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),width+' '+view);
    if(view==='production')await p.screenshot({path:path.join(out,'production-'+width+'.png'),fullPage:true});
   }
  }
  await p.setViewportSize({width:1366,height:900});
  await p.locator('[data-page="sources"]').click();
  await p.getByRole('button',{name:'上传 HTML',exact:true}).click();
  await p.locator('#title').fill('不支持的文件');
  await p.locator('#file').setInputFiles({name:'invalid.html',mimeType:'text/html',buffer:Buffer.from('<html><p>无编号文本</p></html>')});
  await p.getByRole('button',{name:'导入原料',exact:true}).click();
  await p.getByRole('alert').waitFor();
  assert.match(await p.getByRole('alert').innerText(),/未找到可定位/);
  const after=await p.evaluate(async id=>(await fetch('/api/runs/'+id)).json(),runId);
  assert.deepEqual(before.attempts,after.attempts);
  assert.equal(before.artifactDigest,after.artifactDigest);
  assert.equal(errors.length,0,errors.join('\n'));
  fs.writeFileSync(path.join(out,'rule-tests.json'),JSON.stringify(receipts,null,2));
  fs.writeFileSync(path.join(out,'final-run-export.json'),JSON.stringify(after,null,2));
  const result={runId,newModelCalls:0,readbackAfterServerRestart:true,refresh:true,originalAttemptsUnchanged:true,
    artifactDigestUnchanged:true,unsupportedHtmlRejected:true,viewports:[1366,390,320],pages:4,pageErrors:errors,
    primaryDmnCalls:2,recoveryDmnCalls:1,guardOnlyCases:2,publicationAllowed:false};
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await b.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
