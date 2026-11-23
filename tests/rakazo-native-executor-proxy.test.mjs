import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {EventEmitter} from 'node:events';
import {once} from 'node:events';
import {createExecutorProxy,COMPUTER_OPERATION_TIMEOUT_MS} from '../deploy/rakazo/native-executor-proxy.mjs';

test('cold-start transport outlives the controller budget but disconnect cancels the pending request',async()=>{
 let options,body,destroyed=false,started;
 const pending=new Promise(resolve=>{started=resolve;});
 const out=new EventEmitter();out.end=value=>{body=value;started();};out.destroy=()=>{destroyed=true;};
 const proxy=createExecutorProxy({request:(value)=>{options=value;return out;}});
 proxy.listen(0,'127.0.0.1');await once(proxy,'listening');
 const request=http.request({hostname:'127.0.0.1',port:proxy.address().port,path:'/agent/exec',method:'POST'});
 request.on('error',()=>{});
 try{
  const scope={runId:'run',userId:'alice',spaceId:'space',command:'echo safe'};
  request.end(JSON.stringify(scope));await pending;
  assert.equal(options.timeout,COMPUTER_OPERATION_TIMEOUT_MS);assert(options.timeout>540000);
  assert.deepEqual(JSON.parse(body),scope);assert.equal(destroyed,false);
  request.destroy();
  for(let i=0;i<50&&!destroyed;i++)await new Promise(resolve=>setTimeout(resolve,10));
  assert.equal(destroyed,true,'disconnect must cancel a pending long computer startup transport');
 }finally{request.destroy();proxy.closeAllConnections();await new Promise(resolve=>proxy.close(resolve));}
});

test('the startup budget does not weaken operation routing',async()=>{
 let calls=0;const proxy=createExecutorProxy({request:()=>{calls++;throw Error('must not reach upstream');}});
 proxy.listen(0,'127.0.0.1');await once(proxy,'listening');
 try{const response=await fetch('http://127.0.0.1:'+proxy.address().port+'/computers',{method:'POST'});assert.equal(response.status,404);assert.equal(calls,0);}
 finally{proxy.closeAllConnections();await new Promise(resolve=>proxy.close(resolve));}
});
