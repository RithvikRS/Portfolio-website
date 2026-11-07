import test from 'node:test';
import assert from 'node:assert/strict';
import {allowed,createServer} from '../deploy/rakazo/edge.mjs';
const owner={host:'rakazo.144.24.135.201.sslip.io','remote-user':'rithvik','remote-groups':'admins'};
test('pilot excludes other admins and untrusted origins',()=>{
 assert.equal(allowed(owner,'GET'),true);
 for(const h of [{},{...owner,'remote-user':'friend'},{...owner,'remote-groups':'users'},{...owner,host:'evil.example'}])assert.equal(allowed(h,'GET'),false);
 assert.equal(allowed(owner,'POST'),false);
 assert.equal(allowed({...owner,origin:'https://evil.example'},'POST'),false);
 assert.equal(allowed({...owner,origin:'https://rakazo.144.24.135.201.sslip.io'},'POST'),true);
 assert.equal(allowed(owner,'GET',true),false);
});
test('unauthenticated requests cannot reach bridge',async t=>{
 const server=createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));
 const base=`http://127.0.0.1:${server.address().port}`;
 for(const path of ['/','/api/start','/desktop/embed.html'])assert.equal((await fetch(base+path)).status,403);
});
