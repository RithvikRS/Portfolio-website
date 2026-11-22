import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

test('API startup pins runtime limits consistently even with stale deployment environment',()=>{
 const entry=readFileSync(new URL('../deploy/rakazo/entrypoint.mjs',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
 const patch=readFileSync(new URL('../deploy/rakazo/native-assistant.patch',import.meta.url),'utf8');
 const limits=patch.match(/nativeLimits = \{ tokens: (\d+)/);assert.ok(limits);
 const env={NATIVE_ASSISTANT:'true',MAX_TOOL_CALLS_PER_TURN:'8',RAKAZO_LOCAL_MAX_TOKENS:'1024',MODEL_STREAM_TIMEOUT_MS:'55000',WORKSPACE_ONLY:'false',SANDBOX_PROVIDER:'docker',AUTH_PASSWORD_ENABLED:'true'};
 let spawned;
 vm.runInNewContext(entry,{readFileSync:()=> 'synthetic-secret',spawn:(...args)=>{spawned=args;return {on(){},kill(){}};},process:{argv:['node','entrypoint.mjs','api'],env,execPath:'node',on(){}},console});
 assert.equal(spawned[2].env.MAX_TOOL_CALLS_PER_TURN,'0');assert.equal(spawned[2].env.RAKAZO_LOCAL_MAX_TOKENS,limits[1]);
 assert.ok(Number(env.MODEL_STREAM_TIMEOUT_MS)>=61000+55000);assert.ok(Number(env.MODEL_STREAM_IDLE_TIMEOUT_MS)>=61000+55000);
 assert.equal(env.WORKSPACE_ONLY,'true');assert.equal(env.SANDBOX_PROVIDER,'none');assert.equal(env.AUTH_PASSWORD_ENABLED,'false');assert.equal(env.MODEL_STREAM_MAX_RETRIES,'0');
});
