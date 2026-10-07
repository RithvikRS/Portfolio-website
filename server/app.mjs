import { createServer } from 'node:http';
import { readFile, realpath } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createContactHandler } from './contact.mjs';
import { adminIdentity, renderAdmin } from './admin.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg', '.png': 'image/png', '.pdf': 'application/pdf', '.xml': 'application/xml' };
export async function createPortfolioServer({ origin = 'http://127.0.0.1:4173', sendMessage, trustProxy = false, trustedProxyIPs = [], requestLimit, adminEnabled = false, adminUsername = 'rithvik' } = {}) {
  const profile = JSON.parse(await readFile(new URL('../data/portfolio.json', import.meta.url), 'utf8'));
  const publicFiles = new Set(['/', '/index.html', '/Projects.html', '/Awards.html', '/404.html', '/error.html', '/sitemap.xml', '/css/site.css', '/css/admin.css', '/js/site.js', `/${profile.cv}`]);
  const contact = createContactHandler({ sendMessage, origin, trustProxy, trustedProxyIPs, requestLimit });
  const server = createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");
    try {
      const pathname = decodeURIComponent(new URL(req.url, origin).pathname);
      if (pathname === '/admin' || pathname === '/admin/') {
        res.setHeader('Cache-Control', 'no-store');
        res.setHeader('X-Robots-Tag', 'noindex, nofollow');
        const identity = adminIdentity(req, { enabled: adminEnabled && trustProxy, trustedProxyIPs, username: adminUsername });
        if (!identity) { res.writeHead(401, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end('Sign in through the secure workspace to continue.'); return; }
        if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }); res.end(); return; }
        const body = renderAdmin(identity);
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(req.method === 'HEAD' ? undefined : body); return;
      }
      if (pathname === '/api/contact') { await contact(req, res); return; }
      if (req.method !== 'GET' && req.method !== 'HEAD') {
        res.writeHead(405, { Allow: 'GET, HEAD' }); res.end(); return;
      }
      const allowedImage = /^\/images\/[\w.-]+\.(svg|jpg|png)$/i.test(pathname);
      if (!publicFiles.has(pathname) && !allowedImage) throw new Error('Not a public file');
      const file = await realpath(resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`));
      if (!file.startsWith(resolve(root) + sep)) throw new Error('Outside public root');
      let body = await readFile(file);
      if (pathname === '/404.html') body = Buffer.from(body.toString().replace(/<base href="[^"]+">/, '<base href="/">'));
      res.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-cache', 'Content-Length': body.length });
      res.end(req.method === 'HEAD' ? undefined : body);
    } catch {
      const body = (await readFile(new URL('../404.html', import.meta.url), 'utf8')).replace(/<base href="[^"]+">/, '<base href="/">');
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' });
      res.end(req.method === 'HEAD' ? undefined : body);
    }
  });
  server.requestTimeout = 15_000;
  server.headersTimeout = 10_000;
  return server;
}
