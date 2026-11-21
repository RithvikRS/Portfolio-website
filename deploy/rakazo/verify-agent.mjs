// Run only in a disposable, networkless container with the pinned Rakazo image.
import assert from 'node:assert/strict';
import {createPilot} from './agent-pilot.mjs';
const tick=()=>new Promise(r=>setTimeout(r,50));
async function settled(p){const end=Date.now()+70000;while(p.snapshot().busy&&Date.now()<end)await tick();assert.equal(p.snapshot().busy,false);return p.snapshot();}
function stream(delta,finish='stop'){const d={id:'fixture',object:'chat.completion.chunk',created:1,model:'agent-free',choices:[{index:0,delta,finish_reason:null}]};return new Response('data: '+JSON.stringify(d)+'\n\ndata: '+JSON.stringify({...d,choices:[{index:0,delta:{},finish_reason:finish}]})+'\n\ndata: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}});}
let calls=0;
const happy=createPilot({key:'fixture',fetchImpl:async(_url,options)=>{assert.equal(JSON.parse(options.body).max_tokens,256);return ++calls===1?stream({role:'assistant',tool_calls:[{index:0,id:'call',type:'function',function:{name:'lookup_fixture',arguments:'{"name":"inventory"}'}}]},'tool_calls'):stream({role:'assistant',content:'The total is 42.'});}});happy.start();let s=await settled(happy);assert.equal(s.status,'completed');assert.equal(s.toolCalls,1);assert.equal(s.calls,2);assert.match(s.output,/42/);console.log('Native tool round trip passed.');
const huge=createPilot({key:'fixture',fetchImpl:async()=>stream({role:'assistant',content:'x'.repeat(5000)})});huge.start();s=await settled(huge);assert.equal(s.status,'stopped');assert.equal(s.reason,'Output size limit reached');assert.equal(s.output,'');console.log('Native output limit passed.');
let signal;
const stopped=createPilot({key:'fixture',fetchImpl:async(_url,options)=>{signal=options.signal;return new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(Error('cancelled')),{once:true}));}});stopped.start();const until=Date.now()+30000;while(!signal&&Date.now()<until)await tick();assert.ok(signal);stopped.stop();s=await settled(stopped);assert.equal(signal.aborted,true);assert.equal(s.status,'stopped');assert.equal(s.calls,1);console.log('Native in-flight stop passed; no further model calls.');

let noteCalls=0;
const noteText='The selected note records 17 alpha and 25 beta items.';
const summary=createPilot({key:'fixture',fetchImpl:async(_url,options)=>{const body=JSON.parse(options.body);assert.equal(body.tools[0].function.name,'read_selected_note');assert.equal(body.max_tokens,256);if(++noteCalls===1)return stream({role:'assistant',tool_calls:[{index:0,id:'note-call',type:'function',function:{name:'read_selected_note',arguments:'{}'}}]},'tool_calls');assert.ok(JSON.stringify(body.messages).includes(noteText));return stream({role:'assistant',content:'The note describes 42 items.'});}});summary.start({task:{title:'Inventory',notes:noteText}});s=await settled(summary);assert.equal(s.status,'completed');assert.equal(s.toolCalls,1);assert.equal(s.calls,2);console.log('Native selected-note summary passed.');
