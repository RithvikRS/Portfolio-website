import {DatabaseSync} from 'node:sqlite';
import {chmodSync} from 'node:fs';
import {randomUUID,createHash} from 'node:crypto';
export const digest=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const sourceVersion=note=>digest([note.id,note.title,note.notes,note.status]);
export class NoteStore {
 constructor(file,now=()=>Date.now()) {
  this.now=now;this.db=new DatabaseSync(file);
  // Exclusive locking refuses a second controller on the same state volume.
  this.db.exec("PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL; PRAGMA locking_mode=EXCLUSIVE; BEGIN EXCLUSIVE; COMMIT;");
  this.db.exec(`CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, space TEXT NOT NULL, bot TEXT NOT NULL, note TEXT NOT NULL, source TEXT NOT NULL, title TEXT NOT NULL, draft TEXT NOT NULL DEFAULT '', version TEXT, state TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL, saved_id TEXT);
  CREATE TABLE IF NOT EXISTS calls(job TEXT NOT NULL, at INTEGER NOT NULL);
  CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs((1)) WHERE state IN ('running','stopping');`);
  this.db.exec("UPDATE jobs SET state='interrupted' WHERE state IN ('running','stopping'); UPDATE jobs SET state='uncertain' WHERE state='approving';");
  if(file!==':memory:')chmodSync(file,0o600);
 }
 transaction(fn){this.db.exec('BEGIN IMMEDIATE');try{const value=fn();this.db.exec('COMMIT');return value;}catch(e){this.db.exec('ROLLBACK');throw e;}}
 job(id,owner){const row=this.db.prepare('SELECT * FROM jobs WHERE id=? AND owner=?').get(id,owner);if(!row)throw Error('Task unavailable');return row;}
 recent(owner){return this.db.prepare('SELECT * FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 20').all(owner);}
 day(){return Math.floor(this.now()/86400000)*86400000;}
 create(owner,space,bot,note){return this.transaction(()=>{
  if(this.db.prepare("SELECT count(*) AS n FROM jobs WHERE state IN ('running','stopping')").get().n)throw Error('A task is already active');
  if(this.db.prepare('SELECT count(*) AS n FROM jobs WHERE created>=?').get(this.day()).n>=10)throw Error('Daily limit of 10 tasks reached');
  const id=randomUUID(),title=('Summary: '+note.title).slice(0,200);
  this.db.prepare('INSERT INTO jobs(id,owner,space,bot,note,source,title,state,created) VALUES(?,?,?,?,?,?,?,?,?)').run(id,owner,space,bot,note.id,sourceVersion(note),title,'running',this.now());return this.job(id,owner);
 });}
 reserveCall(id,owner){return this.transaction(()=>{const job=this.job(id,owner);if(job.state!=='running'||job.calls>=3)throw Error('Task stopped or call limit reached');
  if(this.db.prepare('SELECT count(*) AS n FROM calls WHERE at>=?').get(this.now()-60000).n>=4)throw Error('Minute request limit reached');
  if(this.db.prepare('SELECT count(*) AS n FROM calls WHERE at>=?').get(this.day()).n>=40)throw Error('Daily request limit reached');
  this.db.prepare('INSERT INTO calls(job,at) VALUES(?,?)').run(id,this.now());this.db.prepare('UPDATE jobs SET calls=calls+1 WHERE id=?').run(id);
 });}
 stop(id,owner){const job=this.job(id,owner);if(['running','stopping','draft'].includes(job.state))this.db.prepare("UPDATE jobs SET state='stopped',draft='',version=NULL WHERE id=?").run(id);return this.job(id,owner);}
 finish(id,owner,view){const job=this.job(id,owner);if(job.state!=='running')return;
  const valid=view.status==='completed'&&view.toolCalls>=1&&view.output.trim()&&view.output.length<=4000;
  const draft=valid?view.output.trim():'';const version=valid?digest([id,job.source,job.title,draft]):null;
  this.db.prepare('UPDATE jobs SET state=?,draft=?,version=? WHERE id=?').run(valid?'draft':'failed',draft,version,id);
 }
 approve(id,owner,version,note){return this.transaction(()=>{const job=this.job(id,owner);if(job.state==='saved')return job;
  if(job.state!=='draft'||job.version!==version||job.source!==sourceVersion(note)||this.now()-job.created>86400000)throw Error('Draft expired, changed, stopped, or already submitted');
  this.db.prepare("UPDATE jobs SET state='approving' WHERE id=?").run(id);return this.job(id,owner);
 });}
 saved(id,noteId){this.db.prepare("UPDATE jobs SET state='saved',saved_id=? WHERE id=? AND state='approving'").run(noteId,id);}
 uncertain(id){this.db.prepare("UPDATE jobs SET state='uncertain' WHERE id=? AND state='approving'").run(id);}
 close(){this.db.close();}
}
