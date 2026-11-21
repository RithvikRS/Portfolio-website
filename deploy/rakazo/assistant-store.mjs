import {DatabaseSync} from 'node:sqlite';
import {chmodSync} from 'node:fs';
import {randomBytes,createHash} from 'node:crypto';

export const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
export function scopeOf(value){
 for(const k of ['user','space','thread','run'])if(typeof value?.[k]!=='string'||! /^[a-zA-Z0-9_-]{1,128}$/.test(value[k]))throw Error('Authenticated scope required');
 return value;
}
export class AssistantStore{
 constructor(file,now=()=>Date.now()){
  this.now=now;this.db=new DatabaseSync(file);this.db.exec(`PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;
   CREATE TABLE IF NOT EXISTS cancelled_runs(id TEXT PRIMARY KEY);
   CREATE TABLE IF NOT EXISTS items(user TEXT,space TEXT,kind TEXT,id TEXT,title TEXT,body TEXT,version INTEGER,updated INTEGER,PRIMARY KEY(user,space,kind,id));
   CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,user TEXT,space TEXT,thread TEXT,run TEXT,action TEXT,payload TEXT,digest TEXT,expires INTEGER,state TEXT);
   CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY,user TEXT,space TEXT,thread TEXT,title TEXT,body TEXT,query TEXT,due INTEGER,repeat_ms INTEGER,state TEXT,last_result TEXT);
   CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY,user TEXT,at INTEGER,state TEXT);
   UPDATE approvals SET state='uncertain' WHERE state='executing';
   UPDATE schedules SET state='paused',last_result='Interrupted delivery; review before resuming' WHERE state='delivering';`);
  if(file!==':memory:')chmodSync(file,0o600);
 }
 transaction(fn){this.db.exec('BEGIN IMMEDIATE');try{const v=fn();this.db.exec('COMMIT');return v;}catch(e){this.db.exec('ROLLBACK');throw e;}}
 list(s,kind){scopeOf(s);return this.db.prepare('SELECT id,title,body,version,updated FROM items WHERE user=? AND space=? AND kind=? ORDER BY updated DESC LIMIT 100').all(s.user,s.space,kind);}
 get(s,kind,id){scopeOf(s);const r=this.db.prepare('SELECT * FROM items WHERE user=? AND space=? AND kind=? AND id=?').get(s.user,s.space,kind,id);if(!r)throw Error('Item not found');return r;}
 put(s,kind,p){
  if(!['memory','document'].includes(kind)||typeof p.title!=='string'||!p.title.trim()||p.title.length>120||typeof p.body!=='string'||Buffer.byteLength(p.body)>(kind==='memory'?2000:32000))throw Error('Invalid item or size limit');
  const id=p.id||randomBytes(12).toString('hex');
  const old=p.id?this.get(s,kind,id):undefined;
  if(old&&old.version!==p.version)throw Error('Item changed; review a fresh proposal');
  if(!old&&this.list(s,kind).length>=100)throw Error('Item limit reached');
  this.db.prepare('INSERT INTO items VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user,space,kind,id) DO UPDATE SET title=excluded.title,body=excluded.body,version=excluded.version,updated=excluded.updated').run(s.user,s.space,kind,id,p.title,p.body,(old?.version||0)+1,this.now());return {id,saved:true};
 }
 remove(s,kind,p){const old=this.get(s,kind,p.id);if(old.version!==p.version)throw Error('Item changed; review a fresh proposal');this.db.prepare('DELETE FROM items WHERE user=? AND space=? AND kind=? AND id=?').run(s.user,s.space,kind,p.id);return {deleted:true};}
 propose(s,action,payload){
  scopeOf(s);if(JSON.stringify(payload).length>40000)throw Error('Proposal too large');
  this.db.prepare("UPDATE approvals SET state='expired' WHERE state='pending' AND expires<?").run(this.now());
  const n=this.db.prepare("SELECT count(*) n FROM approvals WHERE user=? AND state='pending'").get(s.user).n;if(n>=10)throw Error('Review or cancel existing proposals first');
  const id=randomBytes(16).toString('hex'),digest=hash({action,payload});
  this.db.prepare("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?,?,'pending')").run(id,s.user,s.space,s.thread,s.run,action,JSON.stringify(payload),digest,this.now()+15*60000);
  return {id,action,payload,expiresMinutes:15,instruction:'Review the exact proposal below, then send approve '+id+' or reject '+id+' in this chat.'};
 }
 pending(s){return this.db.prepare("SELECT id,action,payload FROM approvals WHERE user=? AND space=? AND thread=? AND run=? AND state='pending'").all(s.user,s.space,s.thread,s.run).map(r=>({...r,payload:JSON.parse(r.payload)}));}
 claim(s,id){return this.transaction(()=>{
  const r=this.db.prepare("SELECT * FROM approvals WHERE id=? AND user=? AND space=? AND thread=? AND state='pending'").get(id,s.user,s.space,s.thread);
  if(!r||r.expires<this.now())throw Error('Approval missing, expired or already used');
  const payload=JSON.parse(r.payload);if(r.digest!==hash({action:r.action,payload}))throw Error('Proposal integrity check failed');
  this.db.prepare("UPDATE approvals SET state='executing' WHERE id=?").run(id);return {...r,payload};
 });}
 finish(id,state){this.db.prepare('UPDATE approvals SET state=? WHERE id=?').run(state,id);}
 reject(s,id){this.db.prepare("UPDATE approvals SET state='rejected' WHERE id=? AND user=? AND space=? AND thread=? AND state='pending'").run(id,s.user,s.space,s.thread);return {rejected:true};}
 cancelled(s){return !!this.db.prepare('SELECT 1 FROM cancelled_runs WHERE id=?').get(s.run);}
 importDocument(s,p){scopeOf(s);if(!/^[a-zA-Z0-9_-]{1,128}$/.test(p.id))throw Error('Invalid upload ID');const old=this.db.prepare('SELECT * FROM items WHERE user=? AND space=? AND kind=\'document\' AND id=?').get(s.user,s.space,p.id);if(old){if(old.title!==p.title||old.body!==p.body)throw Error('Uploaded content differs');return {id:p.id,imported:true};}const result=this.put(s,'document',{title:p.title,body:p.body});this.db.prepare('UPDATE items SET id=? WHERE user=? AND space=? AND kind=\'document\' AND id=?').run(p.id,s.user,s.space,result.id);return {id:p.id,imported:true};}
 cancelRun(s){this.db.prepare('INSERT OR IGNORE INTO cancelled_runs VALUES(?)').run(s.run);this.db.prepare("UPDATE approvals SET state='cancelled' WHERE user=? AND space=? AND thread=? AND run=? AND state='pending'").run(s.user,s.space,s.thread,s.run);}
 schedules(s){return this.db.prepare('SELECT id,title,body,query,due,repeat_ms,state,last_result FROM schedules WHERE user=? AND space=? ORDER BY due LIMIT 20').all(s.user,s.space);}
 schedule(s,p){
  if(this.db.prepare("SELECT count(*) n FROM schedules WHERE user=? AND space=? AND state NOT IN ('deleted','done')").get(s.user,s.space).n>=10)throw Error('Ten active schedules maximum');
  if(typeof p.title!=='string'||p.title.length>120||typeof p.body!=='string'||p.body.length>2000||p.query&&p.query.length>300||!Number.isSafeInteger(p.due)||p.due<this.now()+30000||p.due>this.now()+366*86400000||p.repeat_ms!==0&&(!Number.isSafeInteger(p.repeat_ms)||p.repeat_ms<3600000||p.repeat_ms>31*86400000))throw Error('Invalid schedule; use an explicit future time and at least hourly repeats');
  const id=randomBytes(12).toString('hex');this.db.prepare("INSERT INTO schedules VALUES(?,?,?,?,?,?,?,?,?,'active','')").run(id,s.user,s.space,s.thread,p.title,p.body,p.query||'',p.due,p.repeat_ms);return {id,scheduled:true};
 }
 scheduleState(s,id,state){if(!['paused','active','deleted'].includes(state))throw Error('Invalid schedule state');const row=this.db.prepare('SELECT * FROM schedules WHERE id=? AND user=? AND space=?').get(id,s.user,s.space);if(!row)throw Error('Schedule not found');this.db.prepare('UPDATE schedules SET state=?,due=? WHERE id=?').run(state,Math.max(row.due,this.now()+60000),id);return {id,state};}
 claimDue(){return this.transaction(()=>{
  const r=this.db.prepare("SELECT * FROM schedules WHERE state='active' AND due<=? ORDER BY due LIMIT 1").get(this.now());if(!r)return;
  const n=this.db.prepare('SELECT count(*) n FROM deliveries WHERE user=? AND at>=?').get(r.user,Math.floor(this.now()/86400000)*86400000).n;
  if(n>=10){this.db.prepare("UPDATE schedules SET state='paused',last_result='Daily notification limit reached' WHERE id=?").run(r.id);return;}
  const delivery=randomBytes(12).toString('hex');this.db.prepare("INSERT INTO deliveries VALUES(?,?,?,'attempted')").run(delivery,r.user,this.now());this.db.prepare("UPDATE schedules SET state='delivering' WHERE id=?").run(r.id);return {...r,delivery};
 });}
 delivered(r,ok){this.db.prepare('UPDATE deliveries SET state=? WHERE id=?').run(ok?'sent':'uncertain',r.delivery);this.db.prepare('UPDATE schedules SET state=?,due=?,last_result=? WHERE id=? AND state=\'delivering\'').run(!ok?'paused':r.repeat_ms?'active':'done',r.repeat_ms?this.now()+r.repeat_ms:r.due,ok?'Delivered':'Delivery failed or uncertain; no automatic retry',r.id);}
 close(){this.db.close();}
}
