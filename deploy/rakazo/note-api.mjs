const ORIGIN='https://rakazo.144.24.135.201.sslip.io';
export function identifier(value){if(typeof value!=='string'||!/^[-a-zA-Z0-9_]{1,128}$/.test(value))throw Error('Invalid selection');return value;}
export function createNoteApi(cookie,fetchImpl=fetch){
 if(typeof cookie!=='string'||!cookie||cookie.length>16384||/[\r\n]/.test(cookie))throw Error('Sign in to Rakazo first');
 async function rpc(path,input,space,signal){
  if(!['spaces/list','scratchpad/list','scratchpad/create'].includes(path))throw Error('Operation denied');
  const response=await fetchImpl('http://rakazo_api:3100/rpc/'+path,{method:'POST',redirect:'error',headers:{'Content-Type':'application/json',Cookie:cookie,Origin:ORIGIN,...(space?{'x-rakazo-space-id':identifier(space)}:{})},body:JSON.stringify({json:input}),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(10000)]):AbortSignal.timeout(10000)});
  if(!response.ok){await response.body?.cancel();throw Error(response.status===401||response.status===403?'Sign in to Rakazo or check workspace access':'Workspace request failed');}
  const reader=response.body.getReader();let size=0,parts=[];try{while(true){let {done,value}=await reader.read();if(done)break;if((size+=value.length)>262144)throw Error('Workspace response too large');parts.push(value);}}finally{await reader.cancel();}
  const result=JSON.parse(Buffer.concat(parts).toString('utf8'));if(!Object.hasOwn(result,'json'))throw Error('Unexpected workspace response');return result.json;
 }
 return {spaces:space=>rpc('spaces/list',undefined,space),notes:(space,bot,signal)=>rpc('scratchpad/list',{botId:identifier(bot),includeDone:true},identifier(space),signal),create:(space,bot,title,notes)=>rpc('scratchpad/create',{botId:identifier(bot),title,notes,status:'open'},identifier(space))};
}
export async function selectedNote(api,space,bot,id,signal){const notes=await api.notes(identifier(space),identifier(bot),signal);if(!Array.isArray(notes))throw Error('Unexpected notes response');const note=notes.find(n=>n.id===identifier(id));if(!note||typeof note.title!=='string'||typeof note.notes!=='string')throw Error('Selected note unavailable');if(Buffer.byteLength(note.notes)>8192||note.notes.length>4000)throw Error('Select a note of at most 4000 characters and 8 KiB');return note;}
export async function approveNote(store,api,owner,id,version){const before=store.job(id,owner);const note=await selectedNote(api,before.space,before.bot,before.note);const job=store.approve(id,owner,version,note);if(job.state==='saved')return job;
 try{const saved=await api.create(job.space,job.bot,job.title,job.draft);if(!saved?.id)throw Error('Missing saved note');store.saved(id,saved.id);return store.job(id,owner);}catch{store.uncertain(id);throw Error('Save result uncertain. Check the workspace; this task will not retry saving.');}
}
