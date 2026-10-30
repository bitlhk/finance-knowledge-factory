/* Use an existing Playwright install; no model calls or writes to historical evidence. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async()=>{
 const dir=process.env.PREVIEW_EVIDENCE_DIR || '/home/ubuntu/outputs/knowledge-web-preview-v01';
 fs.mkdirSync(dir,{recursive:true});
 const browser=await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('file://'+path.resolve('web_preview/baseline/v1.5.html'));
 await page.screenshot({path:path.join(dir,'v15-baseline.png'),fullPage:true});
 await page.goto('http://127.0.0.1:61351/');
 await page.getByText('个人贷款制度 · 知识生产车间',{exact:true}).waitFor();
 await page.screenshot({path:path.join(dir,'workshop-1366.png'),fullPage:true});
 await page.getByRole('button',{name:'查看冻结配方',exact:true}).click();
 for(const name of ['目标与来源','工艺与组件','测试与验证','交付与权限']) {
  await page.getByRole('button',{name,exact:true}).click();
  assert.equal(await page.getByRole('dialog').count(),1);
 }
 assert.equal(await page.getByRole('button',{name:'保存 / 发布不可用'}).isDisabled(),true);
 await page.getByRole('button',{name:'关闭',exact:true}).click();
 await page.selectOption('#attempt','P08-1');
 await page.getByRole('button',{name:'冻结验证',exact:true}).click();
 await page.getByRole('heading',{name:'冻结口径结果 · 语义错误'}).waitFor();
 await page.screenshot({path:path.join(dir,'retained-failure.png'),fullPage:true});
 await page.getByRole('button',{name:'原文与锚点',exact:true}).click();
 await page.locator('.selected-quote').waitFor();
 await page.getByRole('button',{name:'知识消费',exact:false}).click();
 await page.selectOption('#attempt','P43-1');
 assert.ok((await page.locator('.raw').first().innerText()).includes('"passed": false'));
 await page.selectOption('#receipt','numeric');
 await page.getByText('独立诊断制品。通过不代表完整条款正确，也不覆盖原候选失败。',{exact:true}).waitFor();
 for(const width of [390,320]) {
  await page.setViewportSize({width,height:844});
  await page.getByRole('button',{name:'知识生产',exact:false}).click();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(dir,`workshop-${width}.png`),fullPage:true});
 }
 const missing=await browser.newPage();
 await missing.route('**/api/snapshot',route=>route.fulfill({status:503,body:'{}'}));
 await missing.goto('http://127.0.0.1:61351/');
 await missing.getByRole('alert').waitFor();
 assert.ok(!(await missing.locator('body').innerText()).includes('数值条件满足'));
 // Browser-only fault injection; no evidence file or historical response is changed.
 const unmatched=await browser.newPage();
 const synthetic=await page.evaluate(async()=>await (await fetch('/api/snapshot')).json());
 synthetic.bundles['P43-1'].parts.coverage.units[0].quote='TEST_ONLY_UNMATCHED_QUOTE';
 await unmatched.route('**/api/snapshot',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(synthetic)}));
 await unmatched.goto('http://127.0.0.1:61351/');
 await unmatched.locator('[data-action="quote"]').first().click();
 await unmatched.getByRole('alert').waitFor();
 assert.equal(await unmatched.locator('.selected-quote').count(),0);
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(dir,'browser-result.json'),JSON.stringify({passed:true,widths:[1366,390,320],errors,
   checks:['four-navigation','four-recipe-steps','source-anchor','unmatched-quote-not-fabricated','retained-failure','separate-numeric-proof','read-only','missing-evidence','responsive']},null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
