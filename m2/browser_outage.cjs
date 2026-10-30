// Explicit fault injection against the exclusive local RAGFlow API container only.
const {chromium}=require('/home/ubuntu/employee-agent-desktop/node_modules/playwright');
const {execFileSync}=require('node:child_process'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const [out,runId]=process.argv.slice(2);if(!out||!/^run-[a-f0-9]{32}$/.test(runId))throw Error('output + run id required');
fs.mkdirSync(out,{recursive:true});
const docker=(...args)=>execFileSync('docker',['--host=unix:///var/run/docker.sock',...args],{stdio:'pipe',timeout:30000});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1187/chrome-linux/chrome',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});let stopped=false;
 const errors=[],posts=[];page.on('pageerror',e=>errors.push(e.message));
 async function query(text){
  await page.locator('#query').fill(text);
  const waiting=page.waitForResponse(r=>r.url().endsWith('/api/search'),{timeout:90000});
  await page.locator('#search-form button').click();
  const response=await waiting;posts.push({status:response.status(),body:await response.json()});
 }
 try{
  await page.goto('http://127.0.0.1:61353/');await page.locator(`[data-run="${runId}"]`).click();
  await page.locator('[data-do="sandbox"]').click();
  await query('合成客服的服务时间是什么？');
  await page.waitForFunction(()=>document.querySelector('.modalbody')?.textContent.includes('Core 查询回执'),null,{timeout:90000});
  assert.equal(posts.at(-1).status,200);
  docker('stop','--time','10','kf-m1-ragflow_api_1');stopped=true;
  await query('申请历史对账单应该怎么办？');
  await page.waitForFunction(()=>document.querySelector('#modal-error')?.textContent.length>0,null,{timeout:60000});
  assert.equal(posts.at(-1).status,409);assert.equal(posts.at(-1).body.error,'RAGFLOW_UNAVAILABLE');
  assert.equal(await page.locator('.modalbody .asset-row').count(),0);
  await page.screenshot({path:path.join(out,'outage.png'),fullPage:true});
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  const before=posts.length;
  await page.reload();await page.locator('[data-page="consume"]').click();
  assert((await page.locator('.content').innerText()).includes('合成客服的服务时间是什么？'));
  assert.equal(posts.length,before);
  await page.screenshot({path:path.join(out,'offline-replay.png'),fullPage:true});
  docker('start','kf-m1-ragflow_api_1');stopped=false;
  let ready=false;
  for(let i=0;i<90;i++){
   try{const r=await fetch('http://127.0.0.1:19380/');if(r.status<500){ready=true;break;}}catch{}
   await new Promise(r=>setTimeout(r,1000));
  }
  assert(ready,'RAGFlow did not recover');
  await page.locator(`[data-query-run="${runId}"]`).click();await query('合成客服的服务时间是什么？');
  await page.waitForFunction(()=>document.querySelector('.modalbody')?.textContent.includes('Core 查询回执'),null,{timeout:90000});
  assert.equal(posts.at(-1).status,200);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASSED',runId,posts,errors,replayIssuedNoSearch:true,recovered:true},null,2));
  console.log(JSON.stringify({status:'PASSED',runId,checks:['native-api-outage','no-stale-answer-on-failure','offline-ui-replay','recovery']}));
 }catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});throw e;}
 finally{if(stopped)docker('start','kf-m1-ragflow_api_1');await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
