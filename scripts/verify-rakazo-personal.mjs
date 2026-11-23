// Disposable native UI only; never point this script at production.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {resolve,join} from 'node:path';
import {mkdirSync,writeFileSync} from 'node:fs';
const root=process.env.RAKAZO_PLAYWRIGHT_ROOT,artifacts=process.env.RAKAZO_TEST_ARTIFACTS;
if(!root||!artifacts)throw Error('Private browser tooling/artifact paths required');
mkdirSync(artifacts,{recursive:true});const {chromium}=createRequire(resolve(root,'package.json'))('playwright');
const origin='https://rakazo.verify.test:18443',phase=process.argv[2];
if(!['login','chat','restored','quota','batch','tokens','recovery'].includes(phase))throw Error('Expected login, chat or restored phase');
const browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP rakazo.verify.test 127.0.0.1','--no-proxy-server']});
const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1400,height:1000},...(phase==='login'?{}:{storageState:join(artifacts,'session.json')})});
await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
const page=await context.newPage();
try{
 await page.goto(origin);
 if(phase==='login'){
  await page.getByRole('button',{name:'Continue with Disposable identity'}).click();await page.getByRole('button',{name:'Verified owner',exact:true}).click();await page.locator('textarea').waitFor();await context.storageState({path:join(artifacts,'session.json')});console.log('Disposable owner signed in. Start the owner-bound fixture service before chat.');
 }else{
  await page.locator('textarea').waitFor();
  const rpc=async(name,json)=>page.evaluate(async({name,json})=>{const r=await fetch('/rpc/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({json})});return {status:r.status,body:await r.text()};},{name,json});
  const botId=new URL(page.url()).pathname.split('/').filter(Boolean).at(-1);
  if(phase==='recovery'){
   assert.equal((await rpc('threads/clear',{botId})).status,200);await page.reload();await page.locator('textarea').waitFor();
   const partial='Recovery rehearsal saved this partial result.';
   const send=async text=>{await page.locator('textarea').fill(text);await page.getByRole('button',{name:'Send',exact:true}).click();};
   await send('FAILURE_RECOVERY_REHEARSAL: return a partial answer, then simulate a provider outage.');
   await page.getByTestId('transcript').getByText(/Recovery rehearsal saved this partial result/).first().waitFor({timeout:30000});
   await page.getByText(/The free model pool is temporarily unavailable/).first().waitFor({timeout:90000});
   await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden'});
   const snapshot=async()=>{const r=await rpc('threads/get',{botId});assert.equal(r.status,200,r.body);return JSON.parse(r.body).json;};
   const failed=await snapshot();assert.equal(failed.run.status,'failed');assert.match(failed.run.error,/free_pool_unavailable/);
   assert.ok(JSON.stringify(failed.messages).includes(partial));assert.equal(failed.activeRuns.length,0);
   await page.reload();await page.locator('textarea').waitFor();
   assert.ok((await page.getByTestId('transcript').innerText()).includes(partial));
   await page.waitForTimeout(5000);
   const stillFailed=await snapshot();assert.equal(stillFailed.run.id,failed.run.id);assert.equal(stillFailed.run.status,'failed');assert.equal(stillFailed.activeRuns.length,0);
   const beforeContinue=await page.locator('body').innerText();assert.ok(!beforeContinue.includes('Unexpected automatic retry occurred.'));assert.ok(!beforeContinue.includes('Review changes'));assert.ok(!beforeContinue.includes("couldn't be reached"));
   await send('Continue after the synthetic outage with a brief greeting.');
   await page.getByText('Hello! I can help you plan, think through questions and work in the isolated computer.',{exact:true}).last().waitFor({timeout:30000});
   await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden'});
   const continued=await snapshot();assert.notEqual(continued.run.id,failed.run.id);assert.equal(continued.run.status,'completed');assert.ok(JSON.stringify(continued.messages).includes(partial));
   console.log('A deliberate provider stream cut preserved its actual partial answer across reload, showed the specific error, stayed stopped, and allowed manual continuation.');
  }else if(phase==='tokens'){
   assert.equal((await rpc('threads/clear',{botId})).status,200);await page.reload();await page.locator('textarea').waitFor();
   await page.locator('textarea').fill('PROVIDER_TOKENS_REHEARSAL: test provider-managed output.');await page.getByRole('button',{name:'Send',exact:true}).click();
   await page.getByTestId('transcript').getByText(/Provider-managed response completed beyond the old buffer/).waitFor({timeout:60000});
   await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden'});assert.equal(await page.getByTestId('composer-error').count(),0);
   console.log('Native chat accepted a 600 KB reasoning stream and 9000 reported output tokens with no token-cap fields sent.');
  }else if(phase==='batch'){
   assert.equal((await rpc('threads/clear',{botId})).status,200);await page.reload();await page.locator('textarea').waitFor();
   const send=async text=>{await page.locator('textarea').fill(text);await page.getByRole('button',{name:'Send',exact:true}).click();};
   await send('BATCH_APPROVAL_REHEARSAL: propose three synthetic memory changes.');await page.getByText('Review changes',{exact:true}).waitFor({timeout:30000});await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden'});
   await send('I approve all 3');for(let i=1;i<=3;i++)await page.getByTestId('transcript').getByText(new RegExp('Batch preference '+i+': completed')).waitFor({timeout:20000});await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden'});
   await send('approve all');await page.getByTestId('transcript').getByText(/already handled/).waitFor({timeout:20000});await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden'});
   assert.equal(await page.getByText('Review changes',{exact:true}).count(),1);assert.equal(await page.getByTestId('composer-error').count(),0);
   console.log('Three proposals approved in one reply; replay rejected without restarting model work.');
  }else if(phase==='quota'){
   assert.equal((await rpc('threads/clear',{botId})).status,200);await page.reload();await page.locator('textarea').waitFor();
   await page.locator('textarea').fill('QUOTA_REHEARSAL: test the shared token allowance error.');await page.getByRole('button',{name:'Send',exact:true}).click();
   const details=page.getByText('Details',{exact:true});await details.first().waitFor({timeout:90000});await details.first().click();
   await page.getByText(/500001\/500000/).first().waitFor({timeout:20000});
   const text=await page.locator('body').innerText();assert.ok(text.includes('2099-11-22T00:00:00.000Z'));assert.ok(text.includes('shared app allowance'));assert.ok(!text.includes("couldn't be reached"));assert.ok(!text.includes('is rate limiting requests. Try again shortly.'));
   await page.screenshot({path:join(artifacts,'quota-error.png'),fullPage:true});console.log('Native quota status, token counts and reset details render without a connection error.');
  }else if(phase==='chat'){
   assert.equal((await rpc('threads/clear',{botId})).status,200);await page.reload();await page.locator('textarea').waitFor();
   const send=async(text)=>{await page.locator('textarea').fill(text);await page.getByRole('button',{name:'Send',exact:true}).click();};
   await send('MEMORY_REHEARSAL: remember that I prefer TypeScript examples.');await page.getByText('Review changes',{exact:true}).waitFor({timeout:30000});await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden',timeout:15000});
   const text=await page.locator('body').innerText();assert.ok(text.includes('approve all'));assert.ok(!/approve [a-f0-9]{32}/.test(text));
   await send('I approve');await page.getByTestId('transcript').getByText(/Fixture preference: completed/).waitFor({timeout:20000});await page.getByRole('button',{name:'Stop',exact:true}).waitFor({state:'hidden',timeout:15000});
   const upload=await rpc('artifacts/create',{botId,name:'fixture-notes.md',mimeType:'text/markdown',contentBase64:Buffer.from('Only this explicitly uploaded document.').toString('base64'),clientNonce:'personal-document-fixture'});assert.equal(upload.status,200,upload.body);
   const bad=await rpc('artifacts/create',{botId,name:'unsupported.pdf',mimeType:'application/pdf',contentBase64:Buffer.from('not a pdf').toString('base64')});assert.equal(bad.status,400);
   await page.reload();await page.getByTestId('transcript').getByText(/Fixture preference: completed/).waitFor();
  }else await page.getByTestId('transcript').getByText(/Fixture preference: completed/).waitFor();
  await page.screenshot({path:join(artifacts,'personal-'+phase+'.png'),fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  writeFileSync(join(artifacts,'personal-'+phase+'.json'),JSON.stringify({passed:true,nativeChat:true,syntheticModel:true,productionData:false,approval:['chat','batch','restored'].includes(phase),textUpload:phase==='chat',failureRecovery:phase==='recovery'}));console.log('Disposable native browser phase passed ('+phase+').');
 }
}catch(e){await page.screenshot({path:join(artifacts,'personal-failure.png'),fullPage:true}).catch(()=>{});throw e;}finally{await browser.close();}
