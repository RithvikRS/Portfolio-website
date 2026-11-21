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
 await send('Hello, help me plan my weekend.');await page.getByText('Hello! I can help you plan, think through questions and work in the isolated computer.',{exact:true}).last().waitFor({timeout:20000});await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden',timeout:15000});
 await send('TOOL_REHEARSAL: calculate 17 plus 25 with the isolated computer.');await page.getByText('The isolated calculation returned 42.',{exact:true}).last().waitFor({timeout:20000});await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden',timeout:15000});
 await send('STOP_REHEARSAL: wait while I test Stop.');const stop=page.getByRole('button',{name:'Stop',exact:true});await stop.waitFor();await page.waitForTimeout(1000);await stop.click();await stop.waitFor({state:'hidden',timeout:15000});
 await page.waitForTimeout(32000);assert.equal(await stop.count(),0);await page.reload();await page.getByText('STOP_REHEARSAL: wait while I test Stop.',{exact:true}).last().waitFor();
 await page.getByText('Model: fixture-primary · model-a',{exact:true}).waitFor();
 await page.getByText('Models used: fixture-primary · model-a; fixture-fallback · model-b',{exact:true}).waitFor();
 await send('LONG_REHEARSAL: perform the six-step isolated task and summarize it.');
 const longStarted=Date.now();await page.getByText('Long task completed after six tools and seven model calls.',{exact:true}).waitFor({timeout:240000});assert.ok(Date.now()-longStarted>120000);await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden'});
 const protectedMethods=await page.evaluate(async()=>{const result={};for(const name of ['models/connect','routines/create','userDevices/list']){const r=await fetch('/rpc/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:'{"json":{}}'});result[name]=r.status;}return result;});assert.ok(Object.values(protectedMethods).every(s=>s===403));
 await page.screenshot({path:join(artifacts,'native-chat-desktop.png'),fullPage:true});await page.setViewportSize({width:390,height:844});await page.screenshot({path:join(artifacts,'native-chat-mobile.png'),fullPage:true});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
 assert.deepEqual(errors,[]);writeFileSync(join(artifacts,'native-result.json'),JSON.stringify({passed:true,nativeUI:true,syntheticModel:true,productionData:false,stop:true,toolResult:true}));console.log('Native chat, tool-result rendering, Stop, reload, restricted routes and mobile layout passed with synthetic inference.');
}catch(e){await page.screenshot({path:join(artifacts,'native-failure.png'),fullPage:true}).catch(()=>{});throw e;}finally{await browser.close();}
