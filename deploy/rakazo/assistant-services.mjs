import http from 'node:http';
import {readFileSync} from 'node:fs';
import {timingSafeEqual,createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {AssistantStore,scopeOf,hash} from './assistant-store.mjs';
import {readPublic,plainText,webSearch} from './assistant-web.mjs';

export class AssistantServices{
 constructor(store,config,{fetcher=fetch,read=readPublic,search=webSearch}={}){this.store=store;this.config=config;this.fetch=fetcher;this.read=read;this.search=search;this.active=new Map();this.notifications=new Map();}
 identity(s){
  scopeOf(s);
  if(s.user===this.config.ownerUserId){if(s.email&&s.email.toLowerCase()!==this.config.ownerEmail?.toLowerCase())throw Error('Identity mismatch');return this.config.ownerEmail;}
  if(!this.config.multiUser||typeof s.email!=='string'||! /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s.email)||s.email.length>254)throw Error('Owner access required');
  return s.email.toLowerCase();
 }
 check(s){this.identity(s);}
 connection(s){const email=this.identity(s);if(s.user===this.config.ownerUserId)return this.config;const c=this.config.users?.[s.user];return c?.email?.toLowerCase()===email?c:{};}
 async authorized(signal,s){
  const email=s?this.identity(s):this.config.ownerEmail;if(!email)throw Error('Directory identity missing');
  const r=await this.fetch('http://access_console:8080/internal/authorize-rakazo',{headers:{'X-Rakazo-Email':email},redirect:'error',signal});
  if(r.status!==204)throw Error('Service access is disabled or unavailable');
 }
 async outline(s,method,payload,signal){
  const c=this.connection(s).outline;if(!c?.token)throw Error('Outline is not connected yet');
  if(!['documents.search','documents.info','documents.create','documents.update','documents.delete'].includes(method))throw Error('Outline method denied');
  const r=await this.fetch('http://outline:3000/api/'+method,{method:'POST',redirect:'error',headers:{Authorization:'Bearer '+c.token,'Content-Type':'application/json','X-Forwarded-Proto':'https'},body:JSON.stringify(payload),signal});
  if(!r.ok)throw Error('Outline request failed ('+r.status+')');const j=await boundedJson(r);if(!j.ok)throw Error('Outline rejected request');return j.data;
 }
 async call(s,action,p,signal){
  this.check(s);if(!p||typeof p!=='object'||Array.isArray(p)||JSON.stringify(p).length>40000)throw Error('Invalid tool parameters');
  signal?.throwIfAborted();if(this.store.cancelled(s))throw Error('Run stopped');
  if(action==='web_search')return this.search(p.query,{signal});
  if(action==='web_read'){const page=await this.read(p.url,{signal});return {url:page.url,text:plainText(page.text).slice(0,16000),untrusted:true};}
  if(action==='memory_list'){const offset=Number.isInteger(p.offset)&&p.offset>=0&&p.offset<=100?p.offset:0;return this.store.list(s,'memory').slice(offset,offset+20);}
  if(action==='document_list')return this.store.list(s,'document').map(({body,...r})=>r);
  if(action==='document_read')return this.store.get(s,'document',p.id);
  if(action==='outline_search')return (await this.outline(s,'documents.search',{query:String(p.query||'').slice(0,300),limit:5},signal)).map(x=>({id:x.document.id,title:x.document.title,url:x.document.url,excerpt:String(x.context||'').slice(0,1500)}));
  if(action==='outline_read'){const d=await this.outline(s,'documents.info',{id:p.id},signal);return {id:d.id,title:d.title,text:String(d.text||'').slice(0,24000),truncated:String(d.text||'').length>24000,updatedAt:d.updatedAt,untrusted:true};}
  if(action==='schedule_list')return this.store.schedules(s);
  if(action==='integration_status')return {web:true,memory:true,documents:true,outline:!!this.connection(s).outline?.token,notifications:!!this.connection(s).ntfy?.authorization,google:'Deferred; future connections will be keyed by user and account. No Google access is enabled.'};
  const actions=['memory_save','memory_delete','document_save','document_delete','outline_create','outline_update','outline_delete','schedule_create','schedule_pause','schedule_resume','schedule_delete'];
  if(!actions.includes(action))throw Error('Tool action denied');
  if(action.startsWith('schedule_')&&!this.connection(s).ntfy?.authorization)throw Error('Private notifications are not connected yet');
  let payload={...p};
  if(action==='schedule_create'){if(!Number.isSafeInteger(p.due))throw Error('Specify an exact future time');payload.dueISO=new Date(p.due).toISOString();payload.dueIndia=new Intl.DateTimeFormat('en-IN',{dateStyle:'full',timeStyle:'long',timeZone:'Asia/Kolkata'}).format(new Date(p.due));}
  if(['outline_update','outline_delete'].includes(action)){
   const d=await this.outline(s,'documents.info',{id:p.id},signal);if(action==='outline_update'&&String(d.text||'').length>24000)throw Error('This document is too large for safe replacement; edit it in Outline');payload={...p,expectedHash:hash({title:d.title,text:d.text,updatedAt:d.updatedAt}),expectedRevision:d.revision,previousTitle:d.title};
  }
  if(action==='outline_create'&&!this.connection(s).outline?.token)throw Error('Outline is not connected yet');
  signal?.throwIfAborted();if(this.store.cancelled(s))throw Error('Run stopped');
  return this.store.propose(s,action,payload);
 }
 async decide(s,command,signal){
  this.check(s);signal?.throwIfAborted();if(this.store.cancelled(s))throw Error('Run stopped');await this.authorized(signal,s);
  const {decision,items}=this.store.decisionItems(s,command);const results=[];
  for(const [index,item] of items.entries()){
   signal?.throwIfAborted();if(this.store.cancelled(s))throw Error('Run stopped');
   try{const result=decision==='approve'?await this.approve(s,item.id,signal):this.store.reject(s,item.id);results.push({title:item.payload.title||item.action,action:item.action,status:decision==='approve'?'completed':'rejected',result});}
   catch(e){results.push({title:item.payload.title||item.action,status:'failed',error:e.message});for(const rest of items.slice(index+1))results.push({title:rest.payload.title||rest.action,status:'not attempted'});break;}
  }
  return results;
 }
 async approve(s,id,signal){
  this.check(s);signal?.throwIfAborted();if(this.store.cancelled(s))throw Error('Run stopped');await this.authorized(signal,s);const r=this.store.claim(s,id),p=r.payload;let external=false;
  try{
   let result;
   const [kind,verb]=r.action.split('_');
   if(['memory','document'].includes(kind))result=this.store.transaction(()=>verb==='save'?this.store.put(s,kind,p):this.store.remove(s,kind,p));
   else if(kind==='outline'){
    if(!this.connection(s).outline?.token)throw Error('Outline is not connected');
    if(verb!=='create'){const d=await this.outline(s,'documents.info',{id:p.id},signal);if(hash({title:d.title,text:d.text,updatedAt:d.updatedAt})!==p.expectedHash)throw Error('Outline document changed; request a fresh proposal');}
    const payload=verb==='create'?{title:p.title,text:p.text,collectionId:p.collectionId,publish:false}:verb==='update'?{id:p.id,title:p.title,text:p.text,lastRevision:p.expectedRevision}:{id:p.id,permanent:false};
    if(verb!=='delete'&&(typeof payload.title!=='string'||payload.title.length>120||typeof payload.text!=='string'||payload.text.length>24000))throw Error('Invalid Outline proposal');
    if(verb==='update'&&!Number.isSafeInteger(p.expectedRevision))throw Error('Outline did not report a revision; refusing an unguarded edit');
    signal?.throwIfAborted();external=true;const d=await this.outline(s,'documents.'+verb,payload,signal);result={completed:true,id:d?.id||p.id};
   }else if(kind==='schedule'){
    result=verb==='create'?this.store.schedule(s,p):this.store.scheduleState(s,p.id,{pause:'paused',resume:'active',delete:'deleted'}[verb]);
    if(verb==='pause'||verb==='delete')this.notifications.get(p.id)?.abort();
   }else throw Error('Approval action denied');
   this.store.finish(id,'completed');return result;
  }catch(e){this.store.finish(id,external?'uncertain':'failed');throw e;}
 }
 async notify(r,signal){
  const s={...r,run:'reminder-'+r.id,email:r.user===this.config.ownerUserId?this.config.ownerEmail:this.config.users?.[r.user]?.email};
  const c=this.connection(s).ntfy;if(!c?.authorization||! /^[a-zA-Z0-9_-]{1,80}$/.test(c.topic))throw Error('Notification configuration missing');
  let message=r.body;
  if(r.query){const d=await this.search(r.query,{signal});message+='\n\nResearch digest (source excerpts):\n'+d.results.map(x=>x.title+'\n'+x.url+'\n'+x.excerpt.slice(0,400)).join('\n\n');}
  await this.authorized(signal,s);
  const full=r.title+'\n\n'+message;const notice=Buffer.byteLength(full)>3800?Buffer.from(full).subarray(0,3800).toString('utf8')+'\n[Digest truncated]':full;
  const response=await this.fetch('https://ntfy.144.24.135.201.sslip.io/'+c.topic,{method:'POST',redirect:'error',signal,headers:{Authorization:c.authorization,'Content-Type':'text/plain; charset=utf-8','Title':'Rakazo reminder','Click':'https://rithvik.ddns.net/rakazo'},body:notice});
  if(!response.ok)throw Error('Notification not accepted');await response.body?.cancel();
 }
 async tick(){
  if(this.busy||!this.config.schedulesEnabled)return;
  this.busy=true;try{
   const r=this.store.claimDue();if(!r)return;
      const controller=new AbortController();this.notifications.set(r.id,controller);
   try{await this.notify(r,AbortSignal.any([controller.signal,AbortSignal.timeout(20000)]));this.store.delivered(r,true);}catch{this.store.delivered(r,false);}finally{this.notifications.delete(r.id);}
  }finally{this.busy=false;}
 }
}
async function boundedJson(r){const reader=r.body.getReader();let n=0;const chunks=[];try{while(true){const{done,value}=await reader.read();if(done)break;if((n+=value.length)>1048576)throw Error('Connector response exceeds limit');chunks.push(value);}}finally{await reader.cancel().catch(()=>{});}return JSON.parse(Buffer.concat(chunks).toString('utf8'));}
export function serve(service){
 return http.createServer(async(req,res)=>{
  if(req.method==='GET'&&req.url==='/healthz'){res.end('{"ok":true}');return;}
  const auth=req.headers.authorization||'';
  if(!service.config.apiToken||!timingSafeEqual(createHash('sha256').update(auth).digest(),createHash('sha256').update('Bearer '+service.config.apiToken).digest())){res.writeHead(401);res.end();return;}
  if(req.method!=='POST'||!['/call','/approve','/reject','/pending','/review','/decide','/cancel','/import'].includes(req.url)){res.writeHead(404);res.end();return;}
  let scope,controller,activeKey;
  try{
   let body='';for await(const c of req){body+=c;if(Buffer.byteLength(body)>65536)throw Error('Request too large');}
   const j=JSON.parse(body);scope=scopeOf(j.scope);service.check(scope);activeKey=JSON.stringify([scope.user,scope.space,scope.thread,scope.run]);
   if(req.url==='/cancel'){
    service.active.get(activeKey)?.abort();service.store.cancelRun(scope);res.end('{"cancelled":true}');return;
   }
   if(service.active.has(activeKey)||service.active.size>=4)throw Error('Assistant tool concurrency limit reached');
   controller=new AbortController();service.active.set(activeKey,controller);
   res.on('close',()=>{if(!res.writableEnded)controller.abort();});const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(25000)]);
   await service.authorized(signal,scope);
   if(service.store.cancelled(scope))throw Error('Run stopped');
   const result=req.url==='/decide'?await service.decide(scope,j.command,signal):req.url==='/review'?service.store.review(scope):req.url==='/import'?service.store.transaction(()=>service.store.importDocument(scope,j.data)):req.url==='/call'?await service.call(scope,j.action,j.data,signal):req.url==='/approve'?await service.approve(scope,j.id,signal):req.url==='/reject'?service.store.reject(scope,j.id):service.store.pending(scope);
   signal.throwIfAborted();res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result));
  }catch(e){res.writeHead(400);res.end(JSON.stringify({error:e.message}));}
  finally{if(scope&&service.active.get(activeKey)===controller)service.active.delete(activeKey);}
 });
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const config=JSON.parse(readFileSync('/run/secrets/rakazo_assistant_config','utf8'));
 config.multiUser=process.env.MULTI_USER_ASSISTANT==='true';
 config.apiToken=readFileSync('/run/secrets/rakazo_assistant_token','utf8').trim();if(config.apiToken.length<32)throw Error('Internal assistant credential missing');
 const service=new AssistantServices(new AssistantStore('/data/assistant.sqlite'),config);
 const server=serve(service);server.maxConnections=16;server.requestTimeout=30000;server.headersTimeout=10000;server.listen(8080,'0.0.0.0');
 const timer=setInterval(()=>void service.tick(),15000);timer.unref();
 for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>{clearInterval(timer);for(const c of [...service.active.values(),...service.notifications.values()])c.abort();server.close(()=>{service.store.close();process.exit(0);});});
}
