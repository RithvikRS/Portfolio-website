// Runs inside the existing networkless controller namespace; never executes on the host.
import {readFileSync,writeFileSync,unlinkSync} from 'node:fs';
export function agentBridge({base,headers,api,getId,setId,fetchImpl=fetch}) {
 let active=null,busy=false,blocked=false,stopping=null;
 const marker=base+'/agent-active.json';
 const valid=v=>typeof v==='string'&&/^[a-zA-Z0-9_-]{1,128}$/.test(v);
 const stop=async runId=>{
  if(active&&active.runId!==runId)throw Error('Run scope mismatch');
  if(stopping)return stopping;if(!active)return;
  const job=active;job.abort.abort();clearTimeout(job.timer);
  stopping=(async()=>{try{if(getId())await api('/computers/'+getId()+'/stop',{});try{unlinkSync(marker);}catch(e){if(e.code!=='ENOENT')throw e;}active=null;}catch{blocked=true;throw Error('Computer stop needs recovery');}finally{stopping=null;}})();
  return stopping;
 };
 // A bridge restart must never leave an abandoned command running.
 const recovery=(async()=>{try{const prior=JSON.parse(readFileSync(marker,'utf8'));if(!valid(prior.runId))throw Error();active={...prior,abort:new AbortController()};await stop(prior.runId);}catch(e){if(e.code!=='ENOENT')blocked=true;}})();
 return {active:()=>!!active,async handle(req,res){
  if(!req.url.startsWith('/agent/'))return false;
  const reply=(status,value)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  try {
   await recovery;if(blocked)throw Error('Isolated computer requires recovery');
   if(req.method!=='POST'||!['/agent/exec','/agent/stop'].includes(req.url)){reply(404,{error:'Denied'});return true;}
   let text='';for await(const chunk of req){text+=chunk;if(Buffer.byteLength(text)>10000)throw Error('Input limit');}
   const body=JSON.parse(text);if(!valid(body.runId))throw Error('Invalid run');
   if(req.url==='/agent/stop'){await stop(body.runId);reply(200,{stopped:true});return true;}
   if(!valid(body.userId)||!valid(body.spaceId)||typeof body.command!=='string'||body.command.length>8192||Object.keys(body).sort().join(',')!=='command,runId,spaceId,userId')throw Error('Invalid command');
   if(busy)throw Error('Computer busy');
   if(active&&(active.runId!==body.runId||active.userId!==body.userId||active.spaceId!==body.spaceId))throw Error('Computer belongs to another run');
   busy=true;
   try {
    if(!active){active={runId:body.runId,userId:body.userId,spaceId:body.spaceId,abort:new AbortController(),tools:0};writeFileSync(marker,JSON.stringify({runId:body.runId,userId:body.userId,spaceId:body.spaceId}),{mode:0o600});active.timer=setTimeout(()=>{void stop(body.runId).catch(()=>{blocked=true;});},120000);}
    const job=active;if(++job.tools>8)throw Error('Tool limit');
    const computer=await api('/computers',{botId:'pilot-owner',spaceId:'pilot-owner-space',homePath:base+'/workspaces/homes/pilot-owner'});setId(computer.id);if(job.abort.signal.aborted){await api('/computers/'+computer.id+'/stop',{});job.abort.signal.throwIfAborted();}
    const response=await fetchImpl('http://127.0.0.1:7091/computers/'+computer.id+'/exec',{method:'POST',headers,body:JSON.stringify({argv:['/bin/sh','-lc',body.command],cwd:'/home/rakazo',timeoutMs:20000}),signal:AbortSignal.any([job.abort.signal,AbortSignal.timeout(25000)])});
    if(!response.ok)throw Error('Computer command rejected');
    const reader=response.body.getReader();let result='',size=0;
    try{while(true){const {done,value}=await reader.read();if(done)break;if((size+=value.length)>24000)throw Error('Computer output limit');result+=Buffer.from(value).toString('utf8');}}finally{await reader.cancel().catch(()=>{});}
    job.abort.signal.throwIfAborted();reply(200,{result});
   }catch(e){await stop(body.runId);throw e;}finally{busy=false;}
  }catch{reply(409,{error:'Isolated command stopped, unavailable or limit reached'});}
  return true;
 }};
}
