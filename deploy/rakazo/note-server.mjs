import http from 'node:http';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {createPilot} from './agent-pilot.mjs';
import {ownerAllowed} from './agent-policy.mjs';
import {NoteStore,sourceVersion} from './note-store.mjs';
import {createNoteApi,selectedNote,approveNote,identifier} from './note-api.mjs';
const owner='rithvik';
export async function requestBody(req){let size=0,parts=[];for await(const part of req){size+=part.length;if(size>1024)throw Error('Request too large');parts.push(part);}const value=JSON.parse(Buffer.concat(parts).toString('utf8')||'{}');if(!value||Array.isArray(value)||typeof value!=='object')throw Error('Invalid request');return value;}
export function createNoteServer({store,pilot,apiFactory=createNoteApi}){return http.createServer(async(req,res)=>{
 const send=(status,value,type='application/json')=>{res.writeHead(status,{'Content-Type':type,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"});res.end(type==='application/json'?JSON.stringify(value):value);};
 if(req.method==='GET'&&req.url==='/healthz')return send(200,{ok:true});
 if(!ownerAllowed(req.headers,req.method))return send(403,{error:'Owner access required'});
 const url=new URL(req.url,'http://pilot');
 try{
  if(req.method==='GET'&&url.pathname==='/')return send(200,readFileSync(new URL('./note-page.html',import.meta.url),'utf8'),'text/html; charset=utf-8');
  if(req.method==='GET'&&url.pathname==='/notes.js')return send(200,readFileSync(new URL('./note-ui.mjs',import.meta.url),'utf8'),'text/javascript');
  if(req.method==='POST'&&url.pathname==='/stop'){
   const input=await requestBody(req),job=store.job(identifier(input.id),owner);
   if(['approving','saved','uncertain'].includes(job.state))throw Error('Save already submitted; check the workspace');
   try{store.stop(job.id,owner);}finally{if(pilot.snapshot().id===job.id)pilot.stop('Stopped by owner');}
   return send(200,{id:job.id,state:store.job(job.id,owner).state});
  }
  const api=apiFactory(req.headers.cookie);
  if(req.method==='GET'&&url.pathname==='/spaces')return send(200,await api.spaces(url.searchParams.get('space')||undefined));
  if(req.method==='GET'&&url.pathname==='/notes'){
   const space=identifier(url.searchParams.get('space')),bot=identifier(url.searchParams.get('bot'));
   const notes=await api.notes(space,bot);const jobs=store.recent(owner).filter(x=>x.space===space&&x.bot===bot);
   const active=pilot.snapshot();return send(200,{notes,jobs,active:jobs.some(x=>x.id===active.id)?active:{busy:active.busy},quota:{runsPerDay:10,callsPerDay:40,callsPerMinute:4}});
  }
  if(req.method==='POST'&&url.pathname==='/start'){
   const input=await requestBody(req);if(Object.keys(input).sort().join(',')!=='bot,note,space')throw Error('Select one note');
   if(pilot.snapshot().busy)throw Error('Another task is still stopping or running');
   const note=await selectedNote(api,input.space,input.bot,input.note);
   const job=store.create(owner,input.space,input.bot,note);
   try{pilot.start({id:job.id,task:{title:note.title,notes:note.notes},hooks:{onCall:async signal=>{const current=await selectedNote(api,job.space,job.bot,job.note,signal);if(sourceVersion(current)!==job.source)throw Error('Source note changed');signal.throwIfAborted();store.reserveCall(job.id,owner);},onStop:()=>store.stop(job.id,owner),onFinish:view=>store.finish(job.id,owner,view)}});}catch(e){store.stop(job.id,owner);throw e;}
   return send(202,store.job(job.id,owner));
  }
  if(req.method==='POST'&&url.pathname==='/approve'){
   const input=await requestBody(req);const job=store.job(identifier(input.id),owner);
   await api.notes(job.space,job.bot); // Recheck the current native session and workspace access.
   return send(200,await approveNote(store,api,owner,job.id,input.version));
  }
  return send(404,{error:'Not found'});
 }catch(error){return send(400,{error:error.message?.startsWith('SQLITE')?'Task storage unavailable':error.message||'Task unavailable'});}
});}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const key=readFileSync('/run/secrets/rakazo_pilot_model_key','utf8').trim();if(!key||/[\r\n\0]/.test(key))throw Error('Missing pilot key');const store=new NoteStore('/data/notes.sqlite'),pilot=createPilot({key}),server=createNoteServer({store,pilot});server.requestTimeout=5000;server.headersTimeout=5000;server.listen(8080,'0.0.0.0');for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>{pilot.stop('Service stopping');server.close();setTimeout(()=>{store.close();process.exit(0);},2000);});}
