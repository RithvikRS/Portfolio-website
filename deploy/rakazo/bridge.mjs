// Fixed owner desktop only. No model API, provider configuration, shell API or jobs.
import http from 'node:http';
import {readFileSync,writeFileSync,unlinkSync,chmodSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
const base='/var/lib/rakazo-pilot';
const env=Object.fromEntries(readFileSync(base+'/controller.env','utf8').trim().split('\n').map(x=>{const i=x.indexOf('=');return[x.slice(0,i),x.slice(i+1)];}));
const headers={'Authorization':'Bearer '+env.SANDBOX_SUPERVISOR_TOKEN,'Content-Type':'application/json','x-rakazo-bot-id':'pilot-owner','x-rakazo-space-id':'pilot-owner-space'};
let id,screen,busy=false;
try {id=JSON.parse(readFileSync(base+'/controller-create-result.json','utf8')).id;}catch{}
async function api(path,body) {
 const response=await fetch('http://127.0.0.1:7091'+path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(540000)});
 if(!response.ok) throw new Error('Controller request failed');return response.json();
}
const page=`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Rakazo · Offline pilot</title><style>body{font:16px system-ui;background:#f5f5ef;color:#173c30;margin:0}main{max-width:1200px;margin:32px auto;padding:0 24px}a{color:inherit}h1{font-size:36px;margin-bottom:8px}.panel{background:white;border:1px solid #d6ded8;border-radius:14px;padding:24px;margin:20px 0}button{background:#173c30;color:white;border:0;border-radius:8px;padding:12px 18px;margin:4px;cursor:pointer}button:disabled{opacity:.45}iframe{width:100%;height:65vh;border:0;background:#222}small{display:block;margin-top:12px;color:#52655b}#status{min-height:24px}</style><main><a href="https://rithvik.ddns.net/admin/">← Your dashboard</a><h1>Rakazo computer</h1><p>Owner-only offline pilot. Model connections and agent jobs are disabled.</p><div class="panel"><strong>1 computer · 1 CPU · 2 GiB RAM · No swap</strong><small>The runtime cache is capped at 8 GiB. Internet, cloud metadata and cluster access are blocked. Treat this desktop as disposable; do not store important files yet.</small><p id="status" role="status">Checking the computer…</p><button id="start">Start / resume</button><button id="view">View screen</button><button id="control">Control screen</button><button id="stop">Stop computer</button><small>Cold creation can take several minutes. Screen sessions reconnect every four minutes to recheck your login. Stopping the computer closes all screens.</small></div><iframe id="screen" title="Offline Rakazo desktop" hidden></iframe></main><script src="/pilot.js"></script></html>`;
const js=`const status=document.querySelector('#status'), frame=document.querySelector('#screen');let mode;const buttons=[...document.querySelectorAll('button')];async function action(name){buttons.forEach(b=>b.disabled=true);status.textContent='Working…';try{const r=await fetch('/api/'+name,{method:'POST'});if(!r.ok)throw Error('Request failed. Refresh or sign in again.');const data=await r.json();status.textContent=data.message||'Ready';if(name==='view'||name==='control'){mode=name;frame.hidden=false;frame.src='/desktop/embed.html?view_only='+(name==='view'?'1':'0');}if(name==='stop'){mode=null;frame.hidden=true;frame.src='about:blank';}}catch(e){status.textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}}buttons.forEach(b=>b.onclick=()=>action(b.id));fetch('/api/status').then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>status.textContent=d.running?'Computer running':'Computer stopped').catch(()=>status.textContent='Pilot unavailable; refresh after signing in.');setInterval(()=>{if(mode)action(mode);},240000);`;
function json(res,status,value){res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(value));}
function target(path){if(!screen)throw Error('Open a screen first');const u=new URL(screen);if(!/^172\.|^192\.168\.|^10\./.test(u.hostname))throw Error('Invalid screen endpoint');const token=new URL(u.searchParams.get('path') || '', 'http://screen/').searchParams.get('token');if(!token)throw Error('Missing screen authorization');u.pathname=path.slice('/desktop'.length);u.search='';if(u.pathname==='/websockify')u.searchParams.set('token',token);return u;}
function proxy(req,res,socket,head){let u;try{u=target(req.url.split('?')[0]);}catch{if(socket)socket.destroy();else json(res,409,{error:'Open the screen first'});return;}
 const h={host:u.host};if(socket)for(const k of ['upgrade','connection','sec-websocket-key','sec-websocket-version','sec-websocket-protocol'])if(req.headers[k])h[k]=req.headers[k];
 const out=http.request(u,{method:'GET',headers:h,timeout:30000});out.on('error',()=>{if(socket)socket.destroy();else{if(!res.headersSent)res.writeHead(502);res.end();}});out.on('timeout',()=>out.destroy());
 if(socket){out.on('upgrade',(r,peer,buffered)=>{socket.write('HTTP/1.1 101 Switching Protocols\r\n'+Object.entries(r.headers).map(([k,v])=>`${k}: ${v}\r\n`).join('')+'\r\n');if(buffered.length)socket.write(buffered);if(head.length)peer.write(head);peer.pipe(socket);socket.pipe(peer);socket.on('close',()=>peer.destroy());socket.on('error',()=>peer.destroy());peer.on('error',()=>socket.destroy());});out.on('response',()=>socket.destroy());}
 else out.on('response',r=>{res.writeHead(r.statusCode,{'content-type':r.headers['content-type']||'application/octet-stream','cache-control':'no-store','content-security-policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; form-action 'none'; base-uri 'none'"});r.pipe(res);});out.end();}
const server=http.createServer(async(req,res)=>{try{
 if(req.method==='GET'&&req.url==='/'){res.writeHead(200,{'content-type':'text/html','cache-control':'no-store'});res.end(page);return;}
 if(req.method==='GET'&&req.url==='/pilot.js'){res.writeHead(200,{'content-type':'text/javascript'});res.end(js);return;}
 if(req.method==='GET'&&req.url==='/api/status'){json(res,200,id?await api('/computers/'+id):{running:false});return;}
 if(req.method==='GET'&&req.url.startsWith('/desktop/')){proxy(req,res);return;}
 if(req.method!=='POST'||!['/api/start','/api/stop','/api/view','/api/control'].includes(req.url)){json(res,404,{error:'Unavailable in this pilot'});return;}
 if(busy){json(res,409,{error:'Another operation is running'});return;}busy=true;
 try{if(req.url==='/api/start'){const r=await api('/computers',{botId:'pilot-owner',spaceId:'pilot-owner-space',homePath:base+'/workspaces/homes/pilot-owner'});id=r.id;writeFileSync(base+'/controller-create-result.json',JSON.stringify(r),{mode:0o600});screen=null;}
 else if(!id)throw Error('Start the computer first');
 else if(req.url==='/api/stop'){await api('/computers/'+id+'/stop',{});screen=null;}
 else{const control=req.url==='/api/control';const r=await api('/computers/'+id+'/screen-mode',{interactive:control,...(control?{controlToken:randomUUID()}: {})});screen=r.screenUrl;}
 json(res,200,{message:req.url==='/api/stop'?'Computer stopped':'Ready'});}finally{busy=false;}
 }catch{json(res,503,{error:'Pilot operation failed. Retry after checking controller health.'});}});
server.on('upgrade',(req,socket,head)=>{if(req.url.split('?')[0]!=='/desktop/websockify'){socket.destroy();return;}proxy(req,null,socket,head);});
const socket=base+'/bridge/bridge.sock';try{unlinkSync(socket);}catch(e){if(e.code!=='ENOENT')throw e;}
server.listen(socket,()=>chmodSync(socket,0o600));
