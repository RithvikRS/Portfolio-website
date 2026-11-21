import test from 'node:test';
import assert from 'node:assert/strict';
import {AssistantStore} from '../deploy/rakazo/assistant-store.mjs';
import {AssistantServices,serve} from '../deploy/rakazo/assistant-services.mjs';
import {publicIPv4,publicUrl,readPublic,plainText} from '../deploy/rakazo/assistant-web.mjs';
const s={user:'owner',space:'space',thread:'thread',run:'run'};
const config={ownerUserId:'owner',ownerEmail:'owner@example.test',outline:{token:'fixture'},ntfy:{authorization:'Bearer fixture',topic:'fixture'},schedulesEnabled:true};
const allow=async url=>{assert.match(url,/authorize-rakazo/);return new Response(null,{status:204});};
test('public reader denies reserved addresses, own nodes and credentials',()=>{
 for(const ip of ['127.0.0.1','10.0.0.1','169.254.169.254','100.64.0.1','172.16.1.1','192.168.1.1','198.18.0.1','224.1.2.3','144.24.135.201','129.225.69.240','::1'])assert.equal(publicIPv4(ip),false,ip);
 assert.equal(publicIPv4('1.1.1.1'),true);
 for(const url of ['http://example.com','https://u:p@example.com','https://localhost','https://x.sslip.io','https://rithvik.ddns.net','https://example.com:8080','https://127.0.0.1'])assert.throws(()=>publicUrl(url));
});
test('DNS private answers are denied before connecting, including mixed answers',async()=>{
 for(const addresses of [['127.0.0.1'],['1.1.1.1','10.0.0.1']])await assert.rejects(readPublic('https://example.com',{resolve:async()=>addresses,request:()=>{throw Error('must not connect')}}),/Private/);
 assert.equal(plainText('<script>evil()</script><p>Hello &amp; world</p>'),'Hello & world');
});
test('writes require bound, single-use approval; rejection, expiry and edited versions fail',async()=>{
 let now=1000000;const st=new AssistantStore(':memory:',()=>now);const api=new AssistantServices(st,config,{fetcher:allow});
 const proposal=await api.call(s,'memory_save',{title:'Preference',body:'Use TypeScript'});
 assert.equal(st.list(s,'memory').length,0);
 await assert.rejects(api.approve({...s,thread:'other'},proposal.id));
 await api.approve(s,proposal.id);assert.equal(st.list(s,'memory')[0].body,'Use TypeScript');await assert.rejects(api.approve(s,proposal.id));
 const exp=await api.call(s,'memory_save',{title:'Later',body:'No'});now+=16*60000;await assert.rejects(api.approve(s,exp.id));
 const item=st.list(s,'memory')[0];const edit=await api.call(s,'memory_save',{id:item.id,version:item.version,title:item.title,body:'Rust'});st.put(s,'memory',{...item,body:'Python'});await assert.rejects(api.approve(s,edit.id),/changed/);
 const reject=await api.call(s,'document_save',{title:'Draft',body:'text'});st.reject(s,reject.id);await assert.rejects(api.approve(s,reject.id));st.close();
});
test('user/space isolation and Stop prevent late proposals and execution',async()=>{
 const st=new AssistantStore(':memory:');const api=new AssistantServices(st,config,{fetcher:allow});st.put(s,'memory',{title:'private',body:'only mine'});
 assert.equal(st.list({...s,user:'other'},'memory').length,0);assert.equal(st.list({...s,space:'other'},'memory').length,0);
 await assert.rejects(api.call({...s,user:'other'},'memory_list',{}),/Owner/);
 const p=await api.call(s,'document_save',{title:'a',body:'b'});st.cancelRun(s);await assert.rejects(api.approve(s,p.id),/stopped/);await assert.rejects(api.call(s,'memory_save',{title:'a',body:'b'}),/stopped/);st.close();
});
test('explicit text imports are idempotent and bounded',()=>{
 const st=new AssistantStore(':memory:');const p={id:'upload1',title:'notes.md',body:'hello'};
 st.importDocument(s,p);st.importDocument(s,p);assert.equal(st.list(s,'document').length,1);
 assert.throws(()=>st.importDocument(s,{...p,body:'different'}));assert.throws(()=>st.importDocument(s,{...p,id:'big',body:'x'.repeat(32001)}));st.close();
});
test('reminders are claimed once, pause on uncertainty, and respect daily budgets',()=>{
 let now=1000000;const st=new AssistantStore(':memory:',()=>now);const r=st.schedule(s,{title:'break',body:'walk',due:now+60000,repeat_ms:3600000});
 now+=60000;const due=st.claimDue();assert.equal(due.id,r.id);assert.equal(st.claimDue(),undefined);st.delivered(due,false);assert.equal(st.schedules(s)[0].state,'paused');
 st.scheduleState(s,r.id,'active');now+=3600000;const next=st.claimDue();st.delivered(next,true);assert.equal(st.schedules(s)[0].due,now+3600000);
 for(let i=0;i<8;i++){now+=3600000;const d=st.claimDue();st.delivered(d,true);}now+=3600000;assert.equal(st.claimDue(),undefined);assert.equal(st.schedules(s)[0].state,'paused');st.close();
});
test('Outline changed document is rejected before a write; Google remains disabled',async()=>{
 const st=new AssistantStore(':memory:');let revision=1,writes=0;const api=new AssistantServices(st,config,{fetcher:async(url)=>{
  if(url.includes('authorize-rakazo'))return new Response(null,{status:204});
  if(url.endsWith('documents.info'))return Response.json({ok:true,data:{id:'d',title:'Title',text:'Body',updatedAt:revision}});
  writes++;return Response.json({ok:true,data:{id:'d'}});
 }});
 const p=await api.call(s,'outline_update',{id:'d',title:'New',text:'New'});revision++;await assert.rejects(api.approve(s,p.id),/changed/);assert.equal(writes,0);
 assert.match((await api.call(s,'integration_status',{})).google,/Deferred/);await assert.rejects(api.call(s,'google_send',{}),/denied/);st.close();
});
import {mkdtempSync,rmSync,copyFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
test('restart and file restore preserve memory while refusing replay of uncertain work',()=>{
 const dir=mkdtempSync(join(tmpdir(),'rakazo-assistant-'));const file=join(dir,'state.sqlite'),copy=join(dir,'restore.sqlite');let now=1000000;
 try{let st=new AssistantStore(file,()=>now);st.put(s,'memory',{title:'durable',body:'remember'});const p=st.propose(s,'document_save',{title:'draft',body:'body'});st.claim(s,p.id);st.schedule(s,{title:'due',body:'reminder',due:now+60000,repeat_ms:0});now+=60000;st.claimDue();st.close();copyFileSync(file,copy);st=new AssistantStore(copy,()=>now);assert.equal(st.list(s,'memory')[0].body,'remember');assert.throws(()=>st.claim(s,p.id));assert.equal(st.schedules(s)[0].state,'paused');assert.equal(st.claimDue(),undefined);st.close();}finally{rmSync(dir,{recursive:true,force:true});}
});
test('revoked owner access blocks approvals and scheduled notifications',async()=>{
 const st=new AssistantStore(':memory:');let sent=0;const api=new AssistantServices(st,config,{fetcher:async url=>{if(url.includes('authorize-rakazo'))return new Response(null,{status:403});sent++;return new Response('{}');}});
 const p=await api.call(s,'memory_save',{title:'no',body:'no'});await assert.rejects(api.approve(s,p.id),/disabled/);await assert.rejects(api.notify({title:'a',body:'b'},AbortSignal.timeout(1000)),/disabled/);assert.equal(sent,0);assert.equal(st.list(s,'memory').length,0);st.close();
});

test('private HTTP bridge requires its own credential and rejects model-driven approval',async()=>{
 const st=new AssistantStore(':memory:');const service=new AssistantServices(st,{...config,apiToken:'fixture-internal-credential'},{fetcher:allow});const server=serve(service);await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port;
 const request=(path,body,token='fixture-internal-credential')=>fetch(url+path,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(body)});
 try{
  let r=await request('/call',{scope:s,action:'memory_list',data:{}},'wrong');assert.equal(r.status,401);await r.text();
  r=await request('/call',{scope:s,action:'memory_list',data:{}});assert.equal(r.status,200);assert.deepEqual(await r.json(),[]);
  r=await request('/call',{scope:s,action:'approve',data:{id:'fake'}});assert.equal(r.status,400);await r.text();
  r=await request('/cancel',{scope:s});assert.equal(r.status,200);await r.text();r=await request('/call',{scope:s,action:'memory_save',data:{title:'a',body:'b'}});assert.equal(r.status,400);await r.text();
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));st.close();}
});
test('late delivery completion cannot reactivate a paused or deleted schedule',()=>{
 let now=1000000;const st=new AssistantStore(':memory:',()=>now);
 for(const state of ['paused','deleted']){const r=st.schedule(s,{title:'race',body:'test',due:now+60000,repeat_ms:3600000});now+=60000;const active=st.claimDue();st.scheduleState(s,r.id,state);st.delivered(active,true);assert.equal(st.schedules(s).find(x=>x.id===r.id).state,state);}st.close();
});
