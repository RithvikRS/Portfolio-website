import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {agentBridge} from '../deploy/rakazo/native-agent-bridge.mjs';

test('isolated command scope, bounded invocation and concurrent Stop',async()=>{
 const base=mkdtempSync(join(tmpdir(),'bridge-'));let id='fixed-computer',stops=0,received;
 const bridge=agentBridge({base,headers:{Authorization:'fixture'},getId:()=>id,setId:v=>id=v,api:async(path)=>{if(path.endsWith('/stop')){stops++;await new Promise(r=>setTimeout(r,20));return {};}return {id};},fetchImpl:async(url,options)=>{received={url,body:JSON.parse(options.body)};return new Response('{"type":"stdout","data":"42"}\n');}});
 const server=http.createServer(async(req,res)=>{if(!await bridge.handle(req,res)){res.writeHead(404);res.end();}});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const request=(path,body)=>fetch('http://127.0.0.1:'+server.address().port+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 try {
  assert.equal((await request('/agent/exec',{runId:'a',userId:'u',spaceId:'s',command:'echo 42'})).status,200);
  assert.deepEqual(received.body,{argv:['/bin/sh','-lc','echo 42'],cwd:'/home/rakazo',timeoutMs:20000});
  assert.equal(received.url,'http://127.0.0.1:7091/computers/fixed-computer/exec');
  assert.equal((await request('/agent/exec',{runId:'a',userId:'other',spaceId:'s',command:'echo nope'})).status,409);
  assert.equal((await request('/agent/stop',{runId:'wrong'})).status,409);
  const both=await Promise.all([request('/agent/stop',{runId:'a'}),request('/agent/stop',{runId:'a'})]);
  assert.ok(both.every(r=>r.status===200));assert.equal(stops,1);assert.equal(bridge.active(),false);
  assert.equal((await request('/agent/docker',{})).status,404);
 }finally{await new Promise(r=>server.close(r));rmSync(base,{recursive:true});}
});

test('stopping during computer startup stops the eventual computer before execution',async()=>{
 const base=mkdtempSync(join(tmpdir(),'bridge-race-'));let release,started;const ready=new Promise(r=>started=r),create=new Promise(r=>release=r);let stops=0,executed=false;
 const bridge=agentBridge({base,headers:{},getId:()=> 'fixed',setId:()=>{},api:async path=>{if(path.endsWith('/stop')){stops++;return {};}started();await create;return {id:'fixed'};},fetchImpl:async()=>{executed=true;return new Response('');}});
 const server=http.createServer(async(req,res)=>{await bridge.handle(req,res);});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const request=(path,body)=>fetch('http://127.0.0.1:'+server.address().port+path,{method:'POST',body:JSON.stringify(body)});
 try{const running=request('/agent/exec',{runId:'a',userId:'u',spaceId:'s',command:'echo bad'});await ready;await request('/agent/stop',{runId:'a'});release();assert.equal((await running).status,409);assert.equal(executed,false);assert.ok(stops>=2);}finally{await new Promise(r=>server.close(r));rmSync(base,{recursive:true});}
});
