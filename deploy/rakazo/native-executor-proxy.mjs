import http from 'node:http';
// Cold computer creation has a 540s controller budget; leave time for its response.
// This transport timeout does not change command runtime or task/token allowances.
export const COMPUTER_OPERATION_TIMEOUT_MS=600000;
// Only the native API shares this internal overlay. The public edge cannot route here.
export function createExecutorProxy({request=http.request}={}){return http.createServer(async(req,res)=>{
 if(req.method==='GET'&&req.url==='/healthz'){res.writeHead(200);res.end('ok');return;}
 if(req.method!=='POST'||!['/agent/exec','/agent/stop'].includes(req.url)){res.writeHead(404);res.end();return;}
 try{let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>10000)throw Error();}
 const out=request({socketPath:'/run/pilot/bridge.sock',path:req.url,method:'POST',headers:{'Content-Type':'application/json'},timeout:COMPUTER_OPERATION_TIMEOUT_MS},r=>{res.writeHead(r.statusCode,{'Content-Type':'application/json','Cache-Control':'no-store'});r.pipe(res);});
 res.on('close',()=>{if(!res.writableEnded)out.destroy();});
 out.on('error',()=>{if(!res.headersSent)res.writeHead(503);res.end();});out.on('timeout',()=>out.destroy());out.end(body);
 }catch{res.writeHead(400);res.end();}
});}
if(process.argv[1]?.endsWith('native-executor-proxy.mjs')){const server=createExecutorProxy();server.requestTimeout=35000;server.headersTimeout=5000;server.listen(8080,'0.0.0.0');}
