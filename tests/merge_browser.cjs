/* Run against the loopback preview only; all mutations use visible page controls. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/home/ubuntu/employee-agent-desktop/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const out=process.argv[2];if(!out)throw Error('Evidence output directory required');
fs.mkdirSync(out,{recursive:true});
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/home/ubuntu/.cache/ms-playwright/chromium-1187/chrome-linux/chrome',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
 const errors=[],calls=[];let completed,query,release;
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',async res=>{if(!res.url().includes('/api/'))return;try{
   const body=await res.json();calls.push({path:new URL(res.url()).pathname,status:res.status(),method:res.request().method()});
   if(new URL(res.url()).pathname==='/api/search'&&res.ok())query=body;
   if(new URL(res.url()).pathname==='/api/document-publish'&&res.ok())release=body;
   if(body.id?.startsWith('run-')&&['COMPLETED','PARTIAL','FAILED'].includes(body.status))completed=body;
 }catch{}});
 try{
  await page.goto(process.argv[3]);await page.locator('[data-do="new-product"]').click();
  await page.locator('#use-upload').click();await page.locator('#title').fill('M2 浏览器合成客服制度');
  await page.locator('#file').setInputFiles(path.join(root,'tests/fixtures/m2-document.html'));
  await page.getByRole('button',{name:'导入原料',exact:true}).click();
  await page.locator('[data-do="recipe"]').click();
  await page.locator('#next').click();assert(await page.locator('#rules-check').isDisabled());
  await page.locator('#next').click();await page.locator('#next').click();
  assert.match(await page.locator('#wizard-error').innerText(),/至少需要/);
  await page.locator('#tests-file').setInputFiles(path.join(out,'questions.json'));
  await page.waitForFunction(()=>document.querySelectorAll('[data-question]').length===3);
  await page.screenshot({path:path.join(out,'recipe.png'),fullPage:true});
  await page.locator('#next').click();await page.locator('#next').click();
  await page.locator('[data-do="start"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-do="approve-document"]')&&!document.querySelector('[data-do="approve-document"]').disabled,null,{timeout:300000});
  assert.equal(completed.status,'COMPLETED');assert.equal(completed.release.state,'VALIDATED');
  assert.equal(completed.artifact.validation.retrievalTests.length,3);
  assert(completed.artifact.validation.retrievalTests.every(t=>t.passed));
  assert.equal(completed.nativeOperations[0].operation,'CONTROLLED_TEST_ONLY');
  assert(await page.locator('[data-do="publish-document"]').isDisabled());
  assert(await page.locator('[data-do="sandbox"]').isDisabled());
  await page.screenshot({path:path.join(out,'candidate.png'),fullPage:true});
  for(const action of ['approve-document','publish-document']){
   await page.locator(`[data-do="${action}"]`).click();
   if(action==='approve-document')await page.locator('#release-reason').fill('固定合成材料，3 条用户提供检索题通过；仅隔离测试，不构成银行业务认可。');
   else assert(await page.locator('#release-reason').evaluate(el=>el.readOnly));
   await page.locator('#release-confirm').check();
   await page.locator('#release-form button').click();await page.locator('#release-form').waitFor({state:'detached'});
  }
  await page.locator('[data-step="validation"]').click();
  assert((await page.locator('.inspect').innerText()).includes('隔离快照已绑定'));
  await page.locator('[data-page="artifacts"]').click();await page.screenshot({path:path.join(out,'artifacts.png'),fullPage:true});
  await page.locator('[data-query-run]').last().click();await page.locator('#query').fill('合成客服服务时间是什么？');
  await page.locator('#search-form button').click();
  await page.waitForFunction(()=>document.querySelector('.modalbody')?.textContent.includes('Core 查询回执'),null,{timeout:90000});
  assert(query.hits.some(h=>h.clause==='第一条'));assert.equal(query.receipt.manifestDigest,release.manifestDigest);
  await page.screenshot({path:path.join(out,'query.png'),fullPage:true});
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  const postsBefore=calls.filter(c=>c.method==='POST').length;
  await page.reload();await page.locator('[data-page="consume"]').click();
  assert((await page.locator('.content').innerText()).includes('合成客服服务时间是什么？'));
  assert.equal(calls.filter(c=>c.method==='POST').length,postsBefore);
  await page.screenshot({path:path.join(out,'history.png'),fullPage:true});
  for(const width of [390,320]){
   await page.setViewportSize({width,height:844});await page.locator('[data-page="production"]').click();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow '+width);
   await page.screenshot({path:path.join(out,`mobile-${width}.png`),fullPage:true});
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASSED',run:completed,release,query,calls,errors,scope:'CONTROLLED_UPSTREAM_BROWSER_CORE_REGRESSION_NOT_NATIVE_RAGFLOW_NOT_HARNESS'},null,2));
  console.log(JSON.stringify({status:'PASSED',runId:completed.id,manifest:release.manifestDigest,evidence:out}));
 }catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({error:e.message,errors,calls,completed},null,2));throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
