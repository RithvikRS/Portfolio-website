import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {agentBridge} from '../deploy/rakazo/native-agent-bridge.mjs';

test('isolated command scope, bounded invocation and concurrent Stop',async()=>{
 const base=mkdtempSync(join(tmpdir(),'bridge-'));let id='fixed-computer',stops=0,received;
 const bridge=agentBridge({base,homePreparer:()=>{},headers:{Authorization:'fixture'},getId:()=>id,setId:v=>id=v,api:async(path)=>{if(path.endsWith('/stop')){stops++;await new Promise(r=>setTimeout(r,20));return {};}return {id};},fetchImpl:async(url,options)=>{received={url,body:JSON.parse(options.body)};return new Response('{"type":"stdout","data":"42"}\n');}});
 const server=http.createServer(async(req,res)=>{if(!await bridge.handle(req,res)){res.writeHead(404);res.end();}});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const request=(path,body)=>fetch('http://127.0.0.1:'+server.address().port+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 try {
  assert.equal((await request('/agent/exec',{runId:'a',userId:'u',spaceId:'s',command:'echo 42'})).status,200);
  assert.deepEqual(received.body,{argv:['/bin/sh','-lc','echo 42'],cwd:'/home/rakazo',timeoutMs:20000});
  assert.equal(received.url,'http://127.0.0.1:7091/computers/fixed-computer/exec');
  assert.equal((await request('/agent/exec',{runId:'a',userId:'other',spaceId:'s',command:'echo nope'})).status,409);
  assert.equal((await request('/agent/stop',{runId:'wrong'})).status,409);
  const both=await Promise.all([request('/agent/stop',{runId:'a',userId:'u',spaceId:'s'}),request('/agent/stop',{runId:'a',userId:'u',spaceId:'s'})]);
  assert.ok(both.every(r=>r.status===200));assert.equal(stops,1);assert.equal(bridge.active(),false);
  assert.equal((await request('/agent/docker',{})).status,404);
 }finally{await new Promise(r=>server.close(r));rmSync(base,{recursive:true});}
});

test('stopping during computer startup stops the eventual computer before execution',async()=>{
 const base=mkdtempSync(join(tmpdir(),'bridge-race-'));let release,started;const ready=new Promise(r=>started=r),create=new Promise(r=>release=r);let stops=0,executed=false;
 const bridge=agentBridge({base,homePreparer:()=>{},headers:{},getId:()=> 'fixed',setId:()=>{},api:async path=>{if(path.endsWith('/stop')){stops++;return {};}started();await create;return {id:'fixed'};},fetchImpl:async()=>{executed=true;return new Response('');}});
 const server=http.createServer(async(req,res)=>{await bridge.handle(req,res);});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const request=(path,body)=>fetch('http://127.0.0.1:'+server.address().port+path,{method:'POST',body:JSON.stringify(body)});
 try{const running=request('/agent/exec',{runId:'a',userId:'u',spaceId:'s',command:'echo bad'});await ready;const stopping=request('/agent/stop',{runId:'a',userId:'u',spaceId:'s'});await new Promise(r=>setTimeout(r,30));release();await stopping;assert.equal((await running).status,409);assert.equal(executed,false);assert.equal(stops,1);}finally{await new Promise(r=>server.close(r));rmSync(base,{recursive:true});}
});


test('executor accepts more than 32 tools and still obeys Stop',async()=>{
 const base=mkdtempSync(join(tmpdir(),'bridge-limit-'));let calls=0,stops=0;
 const bridge=agentBridge({base,homePreparer:()=>{},headers:{},getId:()=> 'fixed',setId:()=>{},api:async path=>{if(path.endsWith('/stop'))stops++;return {id:'fixed'};},fetchImpl:async()=>{calls++;return new Response('ok');}});
 const {Readable}=await import('node:stream');
 const request=async()=>{let status;const req=Readable.from([JSON.stringify({runId:'a',userId:'u',spaceId:'s',command:'true'})]);req.method='POST';req.url='/agent/exec';await bridge.handle(req,{writeHead:n=>status=n,end:()=>{}});return status;};
 try{for(let i=0;i<40;i++)assert.equal(await request(),200);assert.equal(calls,40);assert.equal(stops,0);const req=Readable.from([JSON.stringify({runId:'a',userId:'u',spaceId:'s'})]);req.method='POST';req.url='/agent/stop';await bridge.handle(req,{writeHead:n=>assert.equal(n,200),end:()=>{}});assert.equal(stops,1);assert.equal(bridge.active(),false);}finally{rmSync(base,{recursive:true});}
});

test('executor stays active past ten minutes until explicitly stopped',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});
 const base=mkdtempSync(join(tmpdir(),'bridge-deadline-'));let stopped;const done=new Promise(r=>stopped=r);
 const bridge=agentBridge({base,homePreparer:()=>{},headers:{},getId:()=> 'fixed',setId:()=>{},api:async path=>{if(path.endsWith('/stop'))stopped();return {id:'fixed'};},fetchImpl:async()=>new Response('ok')});
 const {Readable}=await import('node:stream');const req=Readable.from([JSON.stringify({runId:'a',userId:'u',spaceId:'s',command:'true'})]);req.method='POST';req.url='/agent/exec';
 try{await bridge.handle(req,{writeHead:n=>assert.equal(n,200),end:()=>{}});t.mock.timers.tick(120001);assert.equal(bridge.active(),true);t.mock.timers.tick(600000);assert.equal(bridge.active(),true);const stopReq=Readable.from([JSON.stringify({runId:'a',userId:'u',spaceId:'s'})]);stopReq.method='POST';stopReq.url='/agent/stop';await bridge.handle(stopReq,{writeHead:n=>assert.equal(n,200),end:()=>{}});await done;assert.equal(bridge.active(),false);}finally{t.mock.timers.reset();rmSync(base,{recursive:true});}
});

test('homes and supervisor calls are isolated per user and space; manual ID stays untouched',async()=>{
 const {Readable}=await import('node:stream');const base=mkdtempSync(join(tmpdir(),'bridge-scope-'));let creates=[],calls=[],manual=0;
 const bridge=agentBridge({base,homePreparer:()=>{},headers:{Authorization:'fixture','x-rakazo-bot-id':'pilot-owner'},getId:()=> 'manual',setId:()=>manual++,api:async(path,body,headers)=>{calls.push({path,body,headers});if(path==='/computers'){creates.push(body);return {id:'c'+creates.length};}return {};},fetchImpl:async(url,options)=>{calls.push({headers:options.headers});return new Response('ok');}});
 const request=async(path,body)=>{let status;const req=Readable.from([JSON.stringify(body)]);req.method='POST';req.url=path;await bridge.handle(req,{writeHead:n=>status=n,end:()=>{}});return status;};
 try {for(const [userId,spaceId] of [['a','x'],['b','x'],['a','y']]){
  const scope={runId:'r',userId,spaceId};assert.equal(await request('/agent/exec',{...scope,command:'true'}),200);
  assert.equal(await request('/agent/stop',{...scope,userId:'intruder'}),409);
  assert.equal(await request('/agent/stop',scope),200);
  const last=calls.slice(-3);for(const call of last){assert.equal(call.headers['x-rakazo-bot-id'],creates.at(-1).botId);assert.equal(call.headers['x-rakazo-space-id'],spaceId);}
 }assert.equal(new Set(creates.map(c=>c.botId)).size,3);assert.equal(manual,0);for(const c of creates)assert.equal(c.homePath,base+'/workspaces/homes/'+c.botId);
 }finally{rmSync(base,{recursive:true});}
});

test('restart stops only the recorded scoped computer and unknown creation fails closed',async()=>{
 const {writeFileSync}=await import('node:fs');const {Readable}=await import('node:stream');
 for(const known of [true,false]){const base=mkdtempSync(join(tmpdir(),'bridge-recovery-'));const calls=[];
 const prior={userId:'u',spaceId:'s',runId:'r',...(known?{computerId:'owned'}:{})};writeFileSync(join(base,'agent-active.json'),JSON.stringify(prior));
 const bridge=agentBridge({base,homePreparer:()=>{},headers:{},api:async(...args)=>{calls.push(args);return {};},fetchImpl:async()=>new Response('')});
 const req=Readable.from([JSON.stringify({userId:'u',spaceId:'s',runId:'r'})]);req.method='POST';req.url='/agent/stop';let status;
 try{await bridge.handle(req,{writeHead:n=>status=n,end:()=>{}});assert.equal(status,known?200:409);assert.equal(calls.length,known?1:0);if(known){assert.equal(calls[0][0],'/computers/owned/stop');assert.equal(calls[0][2]['x-rakazo-space-id'],'s');}else assert.equal(bridge.active(),true);}finally{rmSync(base,{recursive:true});}}
});
