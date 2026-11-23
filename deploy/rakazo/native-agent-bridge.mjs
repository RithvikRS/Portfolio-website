// Executes only in the networkless controller namespace with scoped supervisor identities.
import {readFileSync,writeFileSync,unlinkSync,renameSync,mkdirSync,lstatSync,chownSync,statSync} from 'node:fs';
import {createHash} from 'node:crypto';
export const sandboxIdentity=({userId,spaceId})=>({botId:'chat-'+createHash('sha256').update(JSON.stringify([userId,spaceId])).digest('hex'),spaceId});
// Namespace uid 1000 maps to the isolated engine's subordinate host uid.
function prepareHome(path,base){
 const homes=statSync(base+'/workspaces/homes'),bounded=statSync(base+'/engine/cache/family-homes');
 if(homes.dev!==bounded.dev||homes.ino!==bounded.ino)throw Error('Bounded home mount unavailable');
 try{mkdirSync(path,{mode:0o700});if(process.platform==='linux'){if(process.getuid()!==0)throw Error('Expected isolated namespace root');chownSync(path,1000,1000);}}catch(e){if(e.code!=='EEXIST')throw e;}
 const stat=lstatSync(path);if(!stat.isDirectory()||stat.isSymbolicLink())throw Error('Unsafe computer home');
}
export function agentBridge({base,headers,api,fetchImpl=fetch,homePreparer=prepareHome}) {
 let active=null,busy=false,blocked=false;
 const marker=base+'/agent-active.json';
 const valid=v=>typeof v==='string'&&/^[a-zA-Z0-9_-]{1,128}$/.test(v);
 const scoped=job=>({...headers,'x-rakazo-bot-id':job.botId,'x-rakazo-space-id':job.spaceId});
 const save=job=>{writeFileSync(marker+'.tmp',JSON.stringify({runId:job.runId,userId:job.userId,spaceId:job.spaceId,computerId:job.computerId}),{mode:0o600});renameSync(marker+'.tmp',marker);};
 const matches=(a,b)=>['runId','userId','spaceId'].every(k=>a[k]===b[k]);
 const stop=async scope=>{
  if(active&&!matches(active,scope))throw Error('Run scope mismatch');
  if(!active)return;
  const job=active;job.abort.abort();
  if(job.stopping)return job.stopping;
  job.stopping=(async()=>{try{
   // Wait for the eventual ID: never stop the shared manual desktop as a substitute.
   if(job.creating)await job.creating;
   if(!valid(job.computerId))throw Error('Unknown computer needs recovery');
   try{await api('/computers/'+job.computerId+'/stop',{},scoped(job));}catch(e){if(e.status!==404)throw e;}
   // Remove only this identity's disposable container layer. The bound home survives.
   // 404 also makes restart recovery safe after deletion succeeded but marker removal failed.
   try{await api('/computers/'+job.computerId,undefined,scoped(job),'DELETE');}catch(e){if(e.status!==404)throw e;}
   try{unlinkSync(marker);}catch(e){if(e.code!=='ENOENT')throw e;}
   if(active===job)active=null;
  }catch{blocked=true;throw Error('Computer stop needs recovery');}})();
  return job.stopping;
 };
 const recovery=(async()=>{try{
  const prior=JSON.parse(readFileSync(marker,'utf8'));
  if(!['runId','userId','spaceId','computerId'].every(k=>valid(prior[k])))throw Error('Incomplete creation marker');
  active={...prior,...sandboxIdentity(prior),abort:new AbortController()};await stop(prior);
 }catch(e){if(e.code!=='ENOENT')blocked=true;}})();
 return {active:()=>blocked||!!active,async handle(req,res){
  if(!req.url.startsWith('/agent/'))return false;
  const reply=(status,value)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  try {
   await recovery;if(blocked)throw Error('Isolated computer requires recovery');
   if(req.method!=='POST'||!['/agent/exec','/agent/stop'].includes(req.url)){reply(404,{error:'Denied'});return true;}
   let text='';for await(const chunk of req){text+=chunk;if(Buffer.byteLength(text)>10000)throw Error('Input limit');}
   const body=JSON.parse(text);if(!['runId','userId','spaceId'].every(k=>valid(body[k])))throw Error('Invalid scope');
   if(req.url==='/agent/stop'){if(Object.keys(body).sort().join(',')!=='runId,spaceId,userId')throw Error('Invalid stop');await stop(body);reply(200,{stopped:true});return true;}
   if(typeof body.command!=='string'||body.command.length>8192||Object.keys(body).sort().join(',')!=='command,runId,spaceId,userId')throw Error('Invalid command');
   if(busy)throw Error('Computer busy');
   if(active&&!matches(active,body))throw Error('Computer belongs to another run');
   busy=true;
   try {
    if(!active){active={runId:body.runId,userId:body.userId,...sandboxIdentity(body),abort:new AbortController()};save(active);}
    const job=active;
    if(!job.computerId){homePreparer(base+'/workspaces/homes/'+job.botId,base);job.creating=(async()=>{const computer=await api('/computers',{botId:job.botId,spaceId:job.spaceId,homePath:base+'/workspaces/homes/'+job.botId},scoped(job));if(!valid(computer.id))throw Error('Invalid computer');job.computerId=computer.id;save(job);})();await job.creating;}
    job.abort.signal.throwIfAborted();
    const response=await fetchImpl('http://127.0.0.1:7091/computers/'+job.computerId+'/exec',{method:'POST',headers:scoped(job),body:JSON.stringify({argv:['/bin/sh','-lc',body.command],cwd:'/home/rakazo',timeoutMs:20000}),signal:AbortSignal.any([job.abort.signal,AbortSignal.timeout(25000)])});
    if(!response.ok)throw Error('Computer command rejected');
    const reader=response.body.getReader();let result='',size=0;
    try{while(true){const {done,value}=await reader.read();if(done)break;if((size+=value.length)>24000)throw Error('Computer output limit');result+=Buffer.from(value).toString('utf8');}}finally{await reader.cancel().catch(()=>{});}
    job.abort.signal.throwIfAborted();reply(200,{result});
   }catch(e){await stop(body);throw e;}finally{busy=false;}
  }catch{reply(409,{error:'Isolated command stopped, unavailable or limit reached'});}
  return true;
 }};
}
