// Uses a real HTTP adapter with an explicit synthetic public-document fixture.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {createInterface}=require('node:readline');
const {mkdirSync,writeFileSync}=require('node:fs');
const assert=require('node:assert/strict');

(async()=>{
  const child=spawn(process.env.PYTHON || 'python3',['tests/serve_public_workbench_fixture.py'],{stdio:['ignore','pipe','inherit']});
  let browser;
  const errors=[],checks=[];
  try {
    const lines=createInterface({input:child.stdout});
    const [url]=await once(lines,'line');
    browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
    mkdirSync('browser-evidence',{recursive:true});
    for(const width of [1440,390]){
      const page=await browser.newPage({viewport:{width,height:900}});
      page.on('pageerror',error=>errors.push(error.message));
      await page.addInitScript(()=>localStorage.setItem('production-run','historical-xss-task'));
      await page.goto(url);
      await page.getByText('暂无可公开的生产任务').waitFor();
      assert.equal(await page.evaluate(()=>localStorage.getItem('production-run')),null);
      assert.equal(await page.locator('[data-run]').count(),0);
      for(const section of ['production','sources','artifacts','consume']){
        await page.locator(`[data-page="${section}"]`).click();
        if(section==='artifacts')await page.locator('[data-publication]').first().waitFor();
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
        await page.screenshot({path:`browser-evidence/${width}-${section}.png`,fullPage:true});
      }
      await page.locator('[data-page="sources"]').click();
      assert.equal(await page.locator('[data-do="upload"]').count(),0);
      await page.locator('.wb-source-group > summary').click();
      await page.locator('[data-publication]').first().click();
      await page.locator('#published-text').waitFor();
      assert.equal(await page.locator('#published-text').innerText(),'Original');
      await page.screenshot({path:`browser-evidence/${width}-original.png`,fullPage:true});
      for(const path of ['/api/sources','/api/runs','/api/document-evaluate','/api/document-source-activate','/api/document-approve','/api/document-publish','/api/search']){
        const result=await page.evaluate(async path=>{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});return {status:r.status,body:await r.json()}},path);
        assert.equal(result.status,403);
        assert.equal(result.body.error,'PUBLIC_WORKBENCH_READ_ONLY');
      }
      checks.push({width,readOnly:true,staleSelectionCleared:true,originalVisible:true});
      await page.close();
    }
    assert.deepEqual(errors,[]);
    writeFileSync('browser-evidence/results.json',JSON.stringify({checks,errors},null,2));
    console.log(JSON.stringify({checks,errors}));
  } finally {
    if(browser)await browser.close();
    child.kill('SIGTERM');
    await once(child,'exit');
  }
})().catch(error=>{console.error(error);process.exitCode=1});
