import http from 'node:http';
if(process.env.VERIFY_RAKAZO_DISPOSABLE!=='1')throw Error('Disposable fixture only');
let calls=0,tools=0,stops=0;
const body=async req=>{let s='';for await(const c of req){s+=c;if(s.length>150000)throw Error();}return JSON.parse(s||'{}');};
http.createServer(async(req,res)=>{
 if(req.url==='/stats'){res.end(JSON.stringify({calls,tools,stops}));return;}
 if(req.url!=='/v1/chat/completions'){res.writeHead(404);res.end();return;}
 const input=await body(req);calls++;
 if(input.model!=='agent-free'||input.max_tokens!==4096){res.writeHead(400);res.end();return;}
 const prompt=JSON.stringify(input.messages.filter(m=>m.role==='user').at(-1)?.content);
 if(prompt.includes('QUOTA_REHEARSAL')){res.writeHead(429,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Token limit exceeded for account: 500001/500000 tokens used in the current window.',code:'token_limit_exceeded',reset_at:'2099-11-22T00:00:00.000Z',retry_after:3600}}));return;}
 const long=prompt.includes('LONG_REHEARSAL');
 if(long){
  const count=input.messages.filter(m=>m.role==='tool').length;
  await new Promise(r=>setTimeout(r,22000));
  if(res.destroyed)return;
  const delta=count<6?{role:'assistant',tool_calls:[{index:0,id:'long-'+count,type:'function',function:{name:'sandbox_shell',arguments:JSON.stringify({command:'echo '+count})}}]}:{role:'assistant',content:'Long task completed after six tools and seven model calls.'};
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.end('data: '+JSON.stringify({id:'long',object:'chat.completion.chunk',model:'agent-free',choices:[{index:0,delta,finish_reason:null}]})+'\n\ndata: '+JSON.stringify({id:'long',object:'chat.completion.chunk',model:'agent-free',choices:[{index:0,delta:{},finish_reason:count<6?'tool_calls':'stop'}]})+'\n\ndata: [DONE]\n\n');return;
 }
 const wait=prompt.includes('STOP_REHEARSAL');
 if(wait)await new Promise(r=>setTimeout(r,30000));
 res.writeHead(200,{'Content-Type':'text/event-stream','x-omniroute-provider':input.messages.some(m=>m.role==='tool')?'fixture-fallback':'fixture-primary','x-omniroute-model':input.messages.some(m=>m.role==='tool')?'model-b':'model-a'});
 const hasResult=input.messages.some(m=>m.role==='tool');
 const personal=prompt.includes('MEMORY_REHEARSAL');
 const tool=(personal||prompt.includes('TOOL_REHEARSAL'))&&!hasResult;
 const delta=tool?{role:'assistant',tool_calls:[{index:0,id:'test-call',type:'function',function:personal?{name:'personal_assistant',arguments:JSON.stringify({action:'memory_save',data:{title:'Fixture preference',body:'Use TypeScript examples'}})}:{name:'sandbox_shell',arguments:'{"command":"python3 -c \\\"print(17+25)\\\""}'}}]}:{role:'assistant',content:hasResult?'The isolated calculation returned 42.':'Hello! I can help you plan, think through questions and work in the isolated computer.'};
 res.end('data: '+JSON.stringify({id:'test-completion',object:'chat.completion.chunk',model:'agent-free',choices:[{index:0,delta,finish_reason:null}]})+'\n\ndata: '+JSON.stringify({id:'test-completion',object:'chat.completion.chunk',model:'agent-free',choices:[{index:0,delta:{},finish_reason:tool?'tool_calls':'stop'}],usage:{prompt_tokens:10,completion_tokens:10,total_tokens:20}})+'\n\ndata: [DONE]\n\n');
}).listen(20128,'0.0.0.0');
http.createServer(async(req,res)=>{if(req.url==='/internal/authorize-rakazo'){res.writeHead(204);res.end();return;}const input=await body(req);if(req.url==='/agent/exec'&&input.runId&&input.userId&&input.spaceId){tools++;res.end(JSON.stringify({result:'42'}));}else if(req.url==='/agent/stop'){stops++;res.end('{"stopped":true}');}else{res.writeHead(404);res.end();}}).listen(8080,'0.0.0.0');
