import http from 'node:http';
// Only the native API shares this internal overlay. The public edge cannot route here.
export function createExecutorProxy(){return http.createServer(async(req,res)=>{
 if(req.method==='GET'&&req.url==='/healthz'){res.writeHead(200);res.end('ok');return;}
 if(req.method!=='POST'||!['/agent/exec','/agent/stop'].includes(req.url)){res.writeHead(404);res.end();return;}
 try{let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>10000)throw Error();}
 const out=http.request({socketPath:'/run/pilot/bridge.sock',path:req.url,method:'POST',headers:{'Content-Type':'application/json'},timeout:30000},r=>{res.writeHead(r.statusCode,{'Content-Type':'application/json','Cache-Control':'no-store'});r.pipe(res);});
 out.on('error',()=>{if(!res.headersSent)res.writeHead(503);res.end();});out.on('timeout',()=>out.destroy());out.end(body);
 }catch{res.writeHead(400);res.end();}
});}
if(process.argv[1]?.endsWith('native-executor-proxy.mjs')){const server=createExecutorProxy();server.requestTimeout=35000;server.headersTimeout=5000;server.listen(8080,'0.0.0.0');}
