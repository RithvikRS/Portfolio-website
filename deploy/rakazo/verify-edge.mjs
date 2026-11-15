// Disposable integration fixture only: never deploy this test identity provider.
import https from 'node:https';
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { createHash, generateKeyPairSync, randomBytes, sign } from 'node:crypto';
if (process.env.VERIFY_RAKAZO_DISPOSABLE !== '1') throw new Error('Disposable opt-in required');
const origin = 'https://rakazo.verify.test:18443';
const issuer = origin + '/idp';
const clientSecret = readFileSync('/run/secrets/rakazo_oidc_secret', 'utf8').trim();
const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const jwk = {...publicKey.export({format:'jwk'}),kid:'disposable',alg:'RS256',use:'sig'};
const codes = new Map(), tokens = new Map();
const json = (res, value, status=200) => {res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(value));};
const escape = value => value.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
const jwt = claims => {
  const head = Buffer.from(JSON.stringify({alg:'RS256',kid:'disposable'})).toString('base64url');
  const body = Buffer.from(JSON.stringify({iss:issuer,aud:'disposable-client',iat:Math.floor(Date.now()/1000),exp:Math.floor(Date.now()/1000)+300,...claims})).toString('base64url');
  return head+'.'+body+'.'+sign('RSA-SHA256',Buffer.from(head+'.'+body),privateKey).toString('base64url');
};
https.createServer({key:readFileSync('/run/secrets/test-key.pem'),cert:readFileSync('/run/secrets/test-ca.pem')},async(req,res)=>{
  const url = new URL(req.url,origin);
  try {
    if(url.pathname==='/idp/.well-known/openid-configuration') return json(res,{issuer,authorization_endpoint:issuer+'/authorize',token_endpoint:issuer+'/token',userinfo_endpoint:issuer+'/userinfo',jwks_uri:issuer+'/jwks',response_types_supported:['code'],subject_types_supported:['public'],id_token_signing_alg_values_supported:['RS256'],token_endpoint_auth_methods_supported:['client_secret_basic','client_secret_post'],code_challenge_methods_supported:['S256']});
    if(url.pathname==='/idp/jwks') return json(res,{keys:[jwk]});
    if(url.pathname==='/idp/authorize') {
      if(url.searchParams.get('redirect_uri')!==origin+'/api/auth/callback/oidc'||url.searchParams.get('client_id')!=='disposable-client'||url.searchParams.get('code_challenge_method')!=='S256') return json(res,{error:'invalid_request'},400);
      res.writeHead(200,{'content-type':'text/html','cache-control':'no-store'});
      return res.end('<!doctype html><html><body><h1>Disposable test identity</h1><form action="/idp/login">'+[...url.searchParams].map(([k,v])=>'<input type="hidden" name="'+escape(k)+'" value="'+escape(v)+'">').join('')+'<button name="identity" value="owner">Verified owner</button><button name="identity" value="outsider">Outsider</button><button name="identity" value="unverified">Unverified owner</button></form></body></html>');
    }
    if(url.pathname==='/idp/login') {
      const redirect=url.searchParams.get('redirect_uri');
      if(redirect!==origin+'/api/auth/callback/oidc') return json(res,{error:'invalid_redirect'},400);
      const identity=url.searchParams.get('identity');
      if(!['owner','outsider','unverified'].includes(identity)) return json(res,{error:'invalid_identity'},400);
      const claims={sub:identity==='outsider'?'outsider':'owner',email:identity==='outsider'?'outsider@example.test':'owner@example.test',email_verified:identity!=='unverified',name:'Disposable owner'};
      const code=randomBytes(24).toString('hex');
      codes.set(code,{claims,challenge:url.searchParams.get('code_challenge'),nonce:url.searchParams.get('nonce')});
      const callback=new URL(redirect);callback.searchParams.set('state',url.searchParams.get('state'));callback.searchParams.set('code',code);
      res.writeHead(302,{location:callback.href,'cache-control':'no-store'});return res.end();
    }
    if(url.pathname==='/idp/token') {
      let body='';for await(const chunk of req){body+=chunk;if(body.length>65536)throw new Error('request too large');}
      const params=new URLSearchParams(body);
      const basic=req.headers.authorization?.startsWith('Basic ')?Buffer.from(req.headers.authorization.slice(6),'base64').toString():null;
      if(basic!==`disposable-client:${clientSecret}`&&!(params.get('client_id')==='disposable-client'&&params.get('client_secret')===clientSecret))return json(res,{error:'invalid_client'},401);
      const code=params.get('code'),entry=codes.get(code);codes.delete(code);
      if(!entry||entry.challenge!==createHash('sha256').update(params.get('code_verifier')??'').digest('base64url'))return json(res,{error:'invalid_grant'},400);
      const token=randomBytes(24).toString('hex');tokens.set(token,entry.claims);
      return json(res,{access_token:token,token_type:'Bearer',expires_in:300,id_token:jwt({...entry.claims,nonce:entry.nonce})});
    }
    if(url.pathname==='/idp/userinfo') {const claims=tokens.get(req.headers.authorization?.replace(/^Bearer /,''));return json(res,claims??{error:'invalid_token'},claims?200:401);}
    if(url.pathname==='/dashboard-exit') {res.writeHead(302,{location:'/dashboard/'});return res.end();}
    if(url.pathname==='/dashboard/') {res.writeHead(200,{'content-type':'text/html'});return res.end('<!doctype html><html><body><h1>Disposable dashboard</h1></body></html>');}
    if(url.pathname==='/computer/') {res.writeHead(200,{'content-type':'text/html'});return res.end('<!doctype html><html><body><h1>Desktop link target only; no computer connected</h1></body></html>');}
    const api = ['/api/','/rpc/'].some(prefix=>url.pathname.startsWith(prefix))||['/ready','/health','/rpc'].includes(url.pathname);
    const headers={...req.headers,host:'rakazo.verify.test:18443','x-forwarded-proto':'https','x-forwarded-host':'rakazo.verify.test:18443'};
    const upstream=http.request({hostname:api?'verify-api':'verify-web',port:api?3100:5173,path:req.url,method:req.method,headers},response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res);});
    upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end('Disposable upstream unavailable');});req.pipe(upstream);
  } catch {if(!res.headersSent)json(res,{error:'fixture_error'},500);else res.end();}
}).listen(18443,'0.0.0.0');
