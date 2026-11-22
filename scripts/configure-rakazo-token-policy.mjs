import {writeFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';

export function providerTokenPolicy(provider,existing={}){
 const fields=['max_tokens','max_completion_tokens','max_output_tokens','maxTokens','maxOutputTokens','thinking'];
 if(provider==='gemini')fields.push('generationConfig');
 if(provider==='kiro')fields.push('inferenceConfig','additionalModelRequestFields');
 const strip=rule=>({...rule,block:[...new Set([...(rule.block||[]),...fields])],allow:(rule.allow||[]).filter(k=>!fields.includes(k))});
 return {...strip(existing),models:Object.fromEntries(Object.entries(existing.models||{}).map(([name,rule])=>[name,strip(rule)])),autoLearn:existing.autoLearn??false};
}
export async function configure({base,token,keyId,backup,fetcher=fetch}){
 if(!token||!keyId||!backup)throw Error('Private management token, inference key ID and backup path required');
 const api=async(path,method='GET',body)=>{const r=await fetcher(base+path,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!r.ok)throw Error('Router policy request failed: '+method+' '+path+' '+r.status);return r.status===204?null:await r.json();};
 const settings=await api('/api/settings');const st=settings.settings||settings;
 if(st.hidePaidModels!==true||st.freeAccessPolicy!=='strict')throw Error('Strict free-only routing must remain enabled');
 const providers=['groq','nvidia','gemini','kiro','openrouter'];const before={filters:{},tokenLimits:await api('/api/usage/token-limits?apiKeyId='+keyId)};
 for(const p of providers)before.filters[p]=await api('/api/providers/'+p+'/param-filters');
 writeFileSync(backup,JSON.stringify(before),{mode:0o600,flag:'wx'});
 for(const p of providers)await api('/api/providers/'+p+'/param-filters','PUT',providerTokenPolicy(p,before.filters[p]));
 await api('/api/keys/'+keyId,'PATCH',{rateLimits:[],compressionEnabled:false});
 const rows=Array.isArray(before.tokenLimits)?before.tokenLimits:before.tokenLimits.limits||before.tokenLimits.tokenLimits;
 if(!Array.isArray(rows))throw Error('Unexpected token-limit schema; inspect privately before continuing');
 for(const row of rows)await api('/api/usage/token-limits?id='+encodeURIComponent(row.id),'DELETE');
 for(const p of providers){const actual=await api('/api/providers/'+p+'/param-filters');for(const field of providerTokenPolicy(p).block)if(!actual.block?.includes(field))throw Error('Router token filter did not persist: '+p);}
 console.log('Free-pool token filters installed; local key quotas and compression disabled. Strict free-only routing retained.');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await configure({base:process.env.OMNIROUTE_URL||'http://127.0.0.1:20128',token:process.env.OMNIROUTE_MANAGEMENT_TOKEN,keyId:process.env.RAKAZO_INFERENCE_KEY_ID,backup:process.env.OMNIROUTE_POLICY_BACKUP});
