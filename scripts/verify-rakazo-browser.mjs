// Run only against the disposable Ampere test edge over a private SSH tunnel.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
const toolRoot=process.env.RAKAZO_PLAYWRIGHT_ROOT;
const artifacts=process.env.RAKAZO_TEST_ARTIFACTS;
if(!toolRoot||!artifacts)throw new Error('Set private browser-tool and artifact directories outside Git.');
const {chromium}=createRequire(resolve(toolRoot,'package.json'))('playwright');
const phase=process.argv[2];
assert.ok(['seed','restore'].includes(phase));
const origin='https://rakazo.verify.test:18443';
await mkdir(artifacts,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP rakazo.verify.test 127.0.0.1','--no-proxy-server']});
let page;
const errors=[],external=[];
const makeContext=async()=>{
  const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.origin!==origin){external.push(url.origin);return route.abort();}
    return route.continue();
  });
  return context;
};
async function login(context,identity='Verified owner'){
  const p=await context.newPage();page=p;
  console.log("Checking browser identity:",identity);
  p.on('pageerror',error=>errors.push(error.message));
  await p.goto(origin,{waitUntil:'networkidle'});
  await p.getByRole('button',{name:'Continue with Disposable identity'}).click();
  await p.getByRole('heading',{name:'Disposable test identity'}).waitFor();
  await p.getByRole('button',{name:identity,exact:true}).click();
  if(identity==='Verified owner')await p.locator('[data-rakazo-surface="workspace-only"]').waitFor({timeout:30000});
  else{
    await p.waitForURL(url=>!url.pathname.startsWith('/idp/')&&!url.pathname.includes('/callback/'),{timeout:30000});
    assert.equal(await p.evaluate(async()=> (await fetch('/rpc/me',{method:'POST',headers:{'content-type':'application/json'},body:'{"json":{}}'})).status),401);
    assert.equal(await p.locator('[data-rakazo-surface="workspace-only"]').count(),0);
  }
  return p;
}
async function waitValue(locator,value){
  await locator.waitFor();
  for(let i=0;i<50;i++){if(await locator.inputValue()===value)return;await new Promise(r=>setTimeout(r,100));}
  assert.equal(await locator.inputValue(),value);
}
try{
  if(phase==='seed'){
    for(const identity of ['Outsider','Unverified owner']){const c=await makeContext();await login(c,identity);await c.close();}
  }
  const context=await makeContext();page=await login(context);
  assert.match(await page.locator('body').innerText(),/Model connections and agent runs are disabled/);
  assert.equal(await page.locator('a[href="/computer/"]').count(),1);
  assert.equal(await page.locator('a[href="/dashboard-exit"]').count(),1);
  let data;
  if(phase==='seed'){
    const suffix=Date.now().toString(36);
    data={workspace:'Restore workspace '+suffix,profile:'Offline researcher '+suffix,title:'Recovery note '+suffix,notes:'Private synthetic note '+suffix,instructions:'Do not execute agents. Preserve this instruction '+suffix};
    await page.locator('#new-workspace').fill(data.workspace);
    await page.getByRole('button',{name:'Create workspace',exact:true}).click();
    await page.getByRole('heading',{name:data.workspace,exact:true}).waitFor();
    await page.locator('#new-profile').fill(data.profile);
    await page.getByRole('button',{name:'Create profile',exact:true}).click();
    await page.locator('#profile-instructions').fill(data.instructions);
    await page.getByRole('button',{name:'Save profile',exact:true}).click();
    await page.getByText('Profile saved.',{exact:true}).waitFor();
    await page.locator('#new-note-title').fill(data.title);
    await page.locator('#new-note-body').fill('Initial synthetic content');
    await page.getByRole('button',{name:'Add note',exact:true}).click();
    const note=page.locator('textarea[id^="note-body-"]');
    await note.waitFor();await note.fill(data.notes);
    await page.getByRole('button',{name:'Save note',exact:true}).click();
    await page.getByText('Saved.',{exact:true}).waitFor();
    await writeFile(join(artifacts,'recovery-expectations.json'),JSON.stringify(data,null,2));
  } else {
    data=JSON.parse(await readFile(join(artifacts,'recovery-expectations.json'),'utf8'));
    await page.getByRole('button',{name:data.workspace,exact:true}).click();
    await page.getByRole('button',{name:data.profile+' Instructions and notes',exact:true}).click();
    await waitValue(page.locator('#profile-instructions'),data.instructions);
    await waitValue(page.locator('textarea[id^="note-body-"]'),data.notes);
    await waitValue(page.locator('input[id^="note-title-"]'),data.title);
  }
  const denied=await page.evaluate(async()=>{
    const out={};for(const path of ['models/connect','threads/send','routines/create','computer/start'])out[path]=(await fetch('/rpc/'+path,{method:'POST',headers:{'content-type':'application/json'},body:'{"json":{}}'})).status;return out;
  });
  assert.ok(Object.values(denied).every(status=>status===403));
  await page.locator('[data-rakazo-surface="workspace-only"]').evaluate(element=>{element.scrollTop=0;});
  await page.screenshot({path:join(artifacts,phase+'-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Mobile page must not overflow horizontally');
  await page.screenshot({path:join(artifacts,phase+'-mobile.png'),fullPage:true});
  if(phase==='restore'){
    page.on('dialog',dialog=>dialog.accept());
    await page.locator('summary').click();
    await page.locator('#workspace-name').fill(data.workspace+' renamed');
    await page.getByRole('button',{name:'Save name',exact:true}).click();
    await page.getByRole('heading',{name:data.workspace+' renamed',exact:true}).waitFor();
    await page.getByRole('button',{name:'Delete note',exact:true}).click();
    await page.locator('textarea[id^="note-body-"]').waitFor({state:'detached'});
    await page.getByRole('button',{name:'Delete profile',exact:true}).click();
    await page.getByText('Profile deleted.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Delete workspace',exact:true}).click();
    await page.getByRole('heading',{name:data.workspace+' renamed',exact:true}).waitFor({state:'detached'});
    assert.equal(await page.getByRole('button',{name:data.workspace+' renamed',exact:true}).count(),0);
  }
  await page.getByRole('button',{name:'Log out',exact:true}).click();
  await page.getByRole('heading',{name:'Disposable dashboard'}).waitFor();
  assert.equal(new URL(page.url()).pathname,'/dashboard/');
  assert.equal(await page.evaluate(async()=> (await fetch('/rpc/me',{method:'POST',headers:{'content-type':'application/json'},body:'{"json":{}}'})).status),401);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  console.log(JSON.stringify({phase,passed:true,identityDenial:phase==='seed',workspaceCRUD:true,restoredData:phase==='restore',renameDeleteChecks:phase==='restore',executionDenied:true,logout:true,mobileOverflow:false,externalRequests:external.length,pageErrors:errors.length}));
} catch(error){
  if(page&&!page.isClosed())console.log("Browser path:",new URL(page.url()).pathname,"Screen:",(await page.locator("body").innerText()).slice(0,1200));
  if(page)await page.screenshot({path:join(artifacts,phase+'-failure.png'),fullPage:true}).catch(()=>{});
  // Do not emit OIDC callback query strings, cookies or tokens.
  console.error(String(error.message).replace(/https:\/\/[^\s"']+/g,'[test URL]').slice(0,2000));
  process.exitCode=1;
}finally{await browser.close();}
