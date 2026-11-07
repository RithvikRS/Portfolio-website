import http from 'node:http';
import { pathToFileURL } from 'node:url';
const origin = 'https://rakazo.144.24.135.201.sslip.io';
export function allowed(headers, method, upgrade = false) {
  if (headers['remote-user'] !== 'rithvik' || !String(headers['remote-groups'] || '').split(',').map(s => s.trim()).includes('admins')) return false;
  if (headers.host !== new URL(origin).host) return false;
  return (!upgrade && ['GET', 'HEAD'].includes(method)) || headers.origin === origin;
}
function proxy(req, res, socket, head) {
  // Never pass browser cookies, credentials, or identity into the computer.
  const headers = { host: 'pilot', 'accept': req.headers.accept || '*/*' };
  if (socket) for (const h of ['upgrade', 'connection', 'sec-websocket-key', 'sec-websocket-version', 'sec-websocket-protocol']) if (req.headers[h]) headers[h] = req.headers[h];
  const upstream = http.request({ socketPath: '/run/pilot/bridge.sock', path: req.url, method: req.method, headers, timeout: 600000 });
  upstream.on('error', () => socket ? socket.destroy() : (!res.headersSent && res.writeHead(503, {'Cache-Control':'no-store'}), res.end('Pilot temporarily unavailable')));
  upstream.on('timeout', () => upstream.destroy());
  if (socket) {
    upstream.on('upgrade', (response, peer, buffered) => {
      socket.write('HTTP/1.1 101 Switching Protocols\r\n' + Object.entries(response.headers).map(([k,v])=>`${k}: ${v}\r\n`).join('') + '\r\n');
      if (buffered.length) socket.write(buffered);
      if (head.length) peer.write(head);
      peer.pipe(socket); socket.pipe(peer);
      const timer = setTimeout(() => {peer.destroy();socket.destroy();}, 240000);
      socket.on('close', () => {clearTimeout(timer);peer.destroy();});
      peer.on('error',()=>socket.destroy()); socket.on('error',()=>peer.destroy());
    });
    upstream.on('response', () => socket.destroy());
  } else upstream.on('response', response => {res.writeHead(response.statusCode, {...response.headers, 'cache-control':'no-store', 'x-content-type-options':'nosniff'});response.pipe(res);});
  req.pipe(upstream);
}
export function createServer() {
  const server = http.createServer((req,res) => {
    if (req.url === '/healthz' && req.method === 'GET') {res.writeHead(200);res.end('ok');return;}
    if (!allowed(req.headers, req.method)) {res.writeHead(403);res.end('Owner access required');return;}
    proxy(req,res);
  });
  server.on('upgrade',(req,socket,head)=>{if(!allowed(req.headers,req.method,true)){socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');return;}proxy(req,null,socket,head);});
  return server;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) createServer().listen(8080,'0.0.0.0');
