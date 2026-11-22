// Disposable compiled API/browser fixture only. Never target a production origin.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {resolve,join} from 'node:path';
import {mkdirSync,writeFileSync} from 'node:fs';
const root=process.env.RAKAZO_PLAYWRIGHT_ROOT,artifacts=process.env.RAKAZO_TEST_ARTIFACTS;
if(!root||!artifacts)throw Error('Private browser tooling and artifact paths required');
mkdirSync(artifacts,{recursive:true});const {chromium}=createRequire(resolve(root,'package.json'))('playwright');
const origin='https://rakazo.verify.test:18443';
const browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP rakazo.verify.test 127.0.0.1','--no-proxy-server']});
const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1400,height:1000}});
await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(origin);await page.getByRole('button',{name:'Continue with Disposable identity'}).click();await page.getByRole('button',{name:'Verified owner',exact:true}).click();
 await page.locator('textarea').waitFor();assert.equal(await page.locator('[data-rakazo-surface="workspace-only"]').count(),0);
 const cleared=await page.evaluate(async()=>{const botId=location.pathname.split('/').filter(Boolean).at(-1);const r=await fetch('/rpc/threads/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({json:{botId}})});return r.status;});assert.equal(cleared,200);await page.reload();await page.locator('textarea').waitFor();
 const send=async text=>{await page.locator('textarea').fill(text);await page.getByRole('button',{name:'Send',exact:true}).click();};
 await send('RUN_LIMIT_REHEARSAL: complete the synthetic 40-tool task.');
 await page.getByText('Completed 40 tools without local usage caps.',{exact:true}).waitFor({timeout:180000});
 assert.equal(await page.getByTestId('composer-error').count(),0);
 await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden'});
 await send('STOP_REHEARSAL: wait while I test Stop.');const stop=page.getByRole('button',{name:'Stop',exact:true});await stop.waitFor();await stop.click();await stop.waitFor({state:'hidden'});await page.waitForTimeout(32000);assert.equal(await stop.count(),0);
 await page.screenshot({path:join(artifacts,'provider-managed-usage.png'),fullPage:true});
 console.log('Native UI completed 40 tools/41 model calls without local quotas, then honored Stop.');
}catch(e){await page.screenshot({path:join(artifacts,'run-limit-failure.png'),fullPage:true}).catch(()=>{});throw e;}finally{await browser.close();}
