import http from 'node:http';
import {fork} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {LIMITS,TOOL,NOTE_TOOL,boundedRequest,boundedResponse,ownerAllowed} from './agent-policy.mjs';
export function createPilot({key,fetchImpl=fetch,spawnWorker=()=>fork(fileURLToPath(new URL('./agent-worker.mjs',import.meta.url)),[],{execArgv:['--import','/app/node_modules/tsx/dist/loader.mjs'],env:{PATH:'/usr/local/bin:/usr/bin:/bin',NODE_ENV:'production',NODE_OPTIONS:'--max-old-space-size=256',MAX_TOOL_CALLS_PER_TURN:'2',MODEL_STREAM_MAX_RETRIES:'0',MODEL_STREAM_TIMEOUT_MS:'25000',MODEL_STREAM_IDLE_TIMEOUT_MS:'25000',LOG_LEVEL:'silent'},stdio:['ignore','ignore','ignore','ipc']})}={}) {
 let active=null, last={status:'idle',calls:0,toolCalls:0,output:''};
 function snapshot(){return {...(active?.view||last),busy:!!active,limits:LIMITS};}
 function stop(reason='Stopped by owner') {
  if(!active)return snapshot();const job=active;
  if(job.abort.signal.aborted)return snapshot();
  try{job.hooks?.onStop?.();}catch{reason='Persistence error; run stopped';}
  job.view.status='stopping';job.view.reason=reason;job.abort.abort();
  if(job.child.connected)job.child.send({type:'stop'});
  if(!job.killTimer)job.killTimer=setTimeout(()=>job.child.kill('SIGKILL'),1000);
  return snapshot();
 }
 function start({id=randomUUID(),task=null,hooks={}}={}){
  if(active)throw Error('A run is already active');
  const job={task,hooks,view:{id,status:'running',calls:0,toolCalls:0,output:'',startedAt:new Date().toISOString()},abort:new AbortController(),pending:new Set(),inflight:false};
  active=job;try{job.child=spawnWorker();}catch{active=null;throw Error('Worker unavailable');}
  job.timer=setTimeout(()=>stop('60-second deadline reached'),LIMITS.durationMs);
  job.child.on('message',message=>{
   if(active!==job||job.abort.signal.aborted)return;
   if(message.type==='ready'){job.child.send({type:'task',task:job.task});}
   else if(message.type==='fetch'){
    const work=(async()=>{try{
      if(job.inflight)throw Error('Concurrent model call denied');
      const body=boundedRequest(message.url,message,job.view.calls,job.task?NOTE_TOOL:TOOL);job.inflight=true;await job.hooks?.onCall?.(job.abort.signal);job.abort.signal.throwIfAborted();job.view.calls++;
      const response=await fetchImpl('http://omniroute:20128/v1/chat/completions',{method:'POST',redirect:'error',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:JSON.stringify(body),signal:job.abort.signal});
      const text=await boundedResponse(response,job.abort.signal);job.abort.signal.throwIfAborted();
      if(job.child.connected)job.child.send({type:'response',id:message.id,body:text});
     }catch(error){stop(['Model call limit reached','Request size limit','Response size limit','Concurrent model call denied'].includes(error.message)?error.message:'Model request stopped');}
     finally{job.inflight=false;}
    })();job.pending.add(work);work.finally(()=>job.pending.delete(work));
   } else if(message.type==='text'){
     if(typeof message.text!=='string'||Buffer.byteLength(job.view.output)+Buffer.byteLength(message.text)>LIMITS.outputBytes){stop('Output size limit reached');return;}
     job.view.output+=message.text;
   } else if(message.type==='tool'){
     if(message.name!==(job.task?NOTE_TOOL.name:TOOL.name)||++job.view.toolCalls>LIMITS.toolCalls)stop('Tool limit reached');
   } else if(message.type==='done'){job.view.status='completed';}
   else if(message.type==='failed')stop('Native runtime stopped');
  });
  job.child.on('error',()=>stop('Worker error'));
  job.child.on('exit',async(code)=>{clearTimeout(job.timer);clearTimeout(job.killTimer);job.abort.abort();await Promise.allSettled([...job.pending]);if(job.view.status!=='completed'||code!==0)job.view.status='stopped';job.view.finishedAt=new Date().toISOString();try{job.hooks?.onFinish?.(job.view);}catch{job.view.status='stopped';job.view.reason='Could not persist draft';}last=job.view;if(active===job)active=null;});
  return snapshot();
 }
 return {snapshot,start,stop};
}
const page=`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Rakazo bounded agent pilot</title><style>body{font:17px system-ui;background:#f5f5ef;color:#173c30;margin:0}main{max-width:760px;margin:40px auto;padding:24px}button{padding:12px 20px;margin:8px 8px 8px 0;border:0;border-radius:8px;background:#173c30;color:white}button:disabled{opacity:.5}pre{white-space:pre-wrap;background:white;padding:20px;border-radius:12px}a{color:inherit}</style><main><a href="/app">Back to Rakazo</a> · <a href="https://rithvik.ddns.net/admin/">Your dashboard</a><h1>Bounded agent pilot</h1><p>Run Rakazo's native agent on a synthetic inventory task. It can read two sample quantities and report their total. It cannot access your workspace, files or desktop.</p><p>One run at a time · 60 seconds · 3 model calls · 256 output tokens per call · 2 tool calls</p><button id="start">Run sample task</button><button id="stop">Stop run</button><p id="status" role="status">Loading…</p><pre id="output"></pre><p>Stop cancels gateway requests and terminates the worker. A provider may still finish a request it already accepted. No new calls are allowed after stop. Results disappear when this service restarts.</p></main><script src="/agent-pilot/pilot.js"></script></html>`;
const js=`const start=document.querySelector('#start'),stop=document.querySelector('#stop'),status=document.querySelector('#status'),output=document.querySelector('#output');async function refresh(){try{const r=await fetch('/agent-pilot/status',{cache:'no-store'});if(!r.ok)throw Error();const d=await r.json();status.textContent=d.status+' · '+d.calls+' model calls · '+d.toolCalls+' tool calls'+(d.reason?' · '+d.reason:'');output.textContent=d.output;start.disabled=d.busy;stop.disabled=!d.busy;}catch{status.textContent='Sign in again to check the run. Runs stop automatically after 60 seconds.';start.disabled=true;}}async function action(name){start.disabled=true;try{const r=await fetch('/agent-pilot/'+name,{method:'POST'});if(!r.ok)throw Error();}catch{status.textContent='Action unavailable; refresh your login.';}await refresh();}start.onclick=()=>action('start');stop.onclick=()=>action('stop');refresh();setInterval(refresh,1000);`;
export function createServer(pilot){return http.createServer((req,res)=>{
 const send=(status,data,type='application/json')=>{res.writeHead(status,{'Content-Type':type,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"});res.end(type==='application/json'?JSON.stringify(data):data);};
 if(req.method==='GET'&&req.url==='/healthz')return send(200,{ok:true});
 if(!ownerAllowed(req.headers,req.method))return send(403,{error:'Owner access required'});
 if(req.headers['transfer-encoding']||Number(req.headers['content-length']||0)!==0)return send(400,{error:'This pilot accepts no input body'});
 if(req.method==='GET'&&req.url==='/')return send(200,page,'text/html; charset=utf-8');
 if(req.method==='GET'&&req.url==='/pilot.js')return send(200,js,'text/javascript');
 if(req.method==='GET'&&req.url==='/status')return send(200,pilot.snapshot());
 if(req.method==='POST'&&req.url==='/start'){try{return send(202,pilot.start());}catch{return send(409,{error:'Run unavailable or already active'});}}
 if(req.method==='POST'&&req.url==='/stop')return send(200,pilot.stop());
 return send(404,{error:'Not found'});
});}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const key=readFileSync('/run/secrets/rakazo_pilot_model_key','utf8').trim();if(!key||/[\r\n\0]/.test(key))throw Error('Missing private pilot key');const pilot=createPilot({key});const server=createServer(pilot);server.requestTimeout=5000;server.headersTimeout=5000;server.listen(8080,'0.0.0.0');for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>{pilot.stop('Service stopping');server.close();setTimeout(()=>process.exit(0),2000);});}
