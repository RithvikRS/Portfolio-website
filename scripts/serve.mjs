import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const publicRoot = fileURLToPath(new URL('../', import.meta.url));
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg', '.png': 'image/png', '.pdf': 'application/pdf', '.json': 'application/json', '.woff2': 'font/woff2' };
const port = Number(process.env.PORT || 4173);
createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://127.0.0.1:${port}`);
    const pathname = decodeURIComponent(url.pathname);
    const file = resolve(publicRoot, `.${pathname}`, pathname.endsWith('/') ? 'index.html' : '');
    if (!file.startsWith(resolve(publicRoot) + sep) || pathname.split('/').some(part => part.startsWith('.'))) {
      res.writeHead(403); res.end('Forbidden'); return;
    }
    await stat(file);
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
    res.end(req.method === 'HEAD' ? undefined : body);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
    const notFound = await readFile(new URL('../404.html', import.meta.url), 'utf8');
    res.end(notFound.replace(/<base href="[^"]+">/, '<base href="/">'));
  }
}).listen(port, '127.0.0.1', () => console.log(`Portfolio preview: http://127.0.0.1:${port}`));
