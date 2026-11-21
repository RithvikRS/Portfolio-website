import {PiAgentRuntime} from '/app/packages/adapters/src/pi-runtime.ts';
import {TOOL,LIMITS} from './agent-policy.mjs';
const pending=new Map();let sequence=0, tools=0;
const abort=new AbortController();
process.on('message',message=>{if(message.type==='stop'){abort.abort();for(const p of pending.values())p.reject(Error('Stopped'));pending.clear();}else if(message.type==='response'){const p=pending.get(message.id);if(!p)return;pending.delete(message.id);message.error?p.reject(Error(message.error)):p.resolve(new Response(message.body,{headers:{'content-type':'text/event-stream'}}));}});
const runtime=new PiAgentRuntime({modelFetch:async(url,options)=>{abort.signal.throwIfAborted();const id=++sequence;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});process.send({type:'fetch',id,url:String(url),method:options?.method,body:options?.body});});}});
try {
 const request={runId:'bounded-pilot',threadId:'synthetic-pilot',botId:'owner-pilot',prompt:'Read inventory with lookup_fixture, add the two quantities and report the total in one short sentence. You must use the tool.',instructions:'You are running a synthetic read-only acceptance test. Use only lookup_fixture. Do not request secrets, run code, browse, delegate, or access files. Finish after reporting the total.',history:[],tools:[TOOL],model:{provider:'openai-compatible',id:'agent-free',baseUrl:'http://127.0.0.1:1/v1',apiKey:'ipc-placeholder',allowPrivateEndpoint:true,maxTokens:256,contextWindow:8192},executeTool:async(name,args)=>{abort.signal.throwIfAborted();if(++tools>LIMITS.toolCalls||name!==TOOL.name||args?.name!=='inventory'||Object.keys(args).length!==1)throw Error('Tool denied');process.send({type:'tool',name});return {items:[{name:'alpha',quantity:17},{name:'beta',quantity:25}]};}};
 for await(const event of runtime.run(request,{signal:abort.signal})){if(event.type==='text')process.send({type:'text',text:event.text});else if(event.type==='error')throw Error('Native runtime failed');}
 process.send({type:'done'});
} catch {process.send({type:'failed',reason:abort.signal.aborted?'Stopped':'Native runtime stopped'});}
finally {process.disconnect();}
