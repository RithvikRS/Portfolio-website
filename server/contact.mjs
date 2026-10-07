import { createHash } from 'node:crypto';
import { isIP } from 'node:net';

const MAX_BYTES = 32 * 1024;
const EMAIL = /^[^\s@<>,;:\x00-\x1f\x7f]+@[^\s@<>,;:\x00-\x1f\x7f]+\.[^\s@<>,;:\x00-\x1f\x7f]+$/;
export const isEmail = value => typeof value === 'string' && value.length <= 254 && EMAIL.test(value);
const problem = (status, message) => Object.assign(new Error(message), { status });

export function validateMessage(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw problem(400, 'Please check the form and try again.');
  if (body.website) throw problem(400, 'This message could not be submitted.');
  const field = (name, min, max, singleLine = true) => {
    if (typeof body[name] !== 'string') throw problem(400, `Please check your ${name}.`);
    const value = body[name].trim();
    const controls = singleLine ? /[\x00-\x1f\x7f]/ : /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/;
    if (value.length < min || value.length > max || controls.test(value)) throw problem(400, `Please check your ${name}.`);
    return value;
  };
  const name = field('name', 2, 80);
  const email = field('email', 3, 254);
  const subject = field('subject', 0, 120);
  const message = field('message', 10, 5000, false);
  if (!isEmail(email)) throw problem(400, 'Please enter a valid email address.');
  if (typeof body.requestId !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(body.requestId)) throw problem(400, 'Please reopen the form and try again.');
  return { name, email, subject, message, requestId: body.requestId };
}

async function readBody(req) {
  if (!/^application\/json(?:;|$)/i.test(req.headers['content-type'] || '')) throw problem(415, 'Please submit through the contact form.');
  if (Number(req.headers['content-length']) > MAX_BYTES) throw problem(413, 'Your message is too large.');
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BYTES) throw problem(413, 'Your message is too large.');
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw problem(400, 'Please check the form and try again.'); }
}

const normalizeIP = value => value.startsWith('::ffff:') && isIP(value.slice(7)) === 4 ? value.slice(7) : value;

function clientIP(req, trustedProxies) {
  const peer = normalizeIP(req.socket.remoteAddress || 'unknown');
  const forwarded = req.headers['x-real-ip'];
  return trustedProxies.has(peer) && typeof forwarded === 'string' && isIP(forwarded) ? normalizeIP(forwarded) : peer;
}

export function createContactHandler({ sendMessage, origin, trustProxy = false, trustedProxyIPs = [], now = Date.now, requestLimit = 5 }) {
  if (!Array.isArray(trustedProxyIPs) || trustedProxyIPs.some(ip => typeof ip !== 'string' || !isIP(ip))) throw new Error('TRUSTED_PROXY_IPS must contain only IP addresses.');
  const trustedProxies = new Set(trustProxy ? ['127.0.0.1', '::1', ...trustedProxyIPs.map(normalizeIP)] : []);
  const clients = new Map();
  const deliveries = new Map();
  let globalWindow = { count: 0, expires: 0 };
  let inFlight = 0;
  const reply = (res, status, body) => {
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(body));
  };
  return async (req, res) => {
    if (req.method === 'GET') return reply(res, 200, { available: Boolean(sendMessage) });
    if (req.method !== 'POST') {
      res.setHeader('Allow', 'GET, POST');
      return reply(res, 405, { error: 'Method not allowed.' });
    }
    try {
      if (req.headers.origin !== origin) throw problem(403, 'Please submit through the contact form on this website.');
      if (!sendMessage) throw problem(503, 'Messaging is temporarily unavailable. Please connect on LinkedIn.');
      const time = now();
      for (const [key, value] of clients) if (value.expires <= time) clients.delete(key);
      for (const [key, value] of deliveries) if (value.expires <= time && !value.pending) deliveries.delete(key);
      const ip = clientIP(req, trustedProxies);
      const client = clients.get(ip) || { count: 0, expires: time + 15 * 60_000 };
      if (globalWindow.expires <= time) globalWindow = { count: 0, expires: time + 60 * 60_000 };
      if (client.count >= requestLimit || globalWindow.count >= 100 || clients.size >= 5000 && !clients.has(ip)) {
        res.setHeader('Retry-After', '900');
        throw problem(429, 'Too many attempts. Please try again later or connect on LinkedIn.');
      }
      client.count++; globalWindow.count++; clients.set(ip, client);
      const data = validateMessage(await readBody(req));
      const fingerprint = createHash('sha256').update(JSON.stringify(data)).digest('hex');
      const existing = deliveries.get(data.requestId);
      if (existing) {
        if (existing.fingerprint !== fingerprint) throw problem(409, 'Your message changed. Please edit a field and try again.');
        try { await existing.promise; }
        catch { throw problem(502, 'Delivery could not be confirmed. Please connect on LinkedIn if you need to follow up.'); }
        return reply(res, 200, { ok: true });
      }
      if (inFlight >= 3 || deliveries.size >= 500) throw problem(503, 'Messaging is busy. Please try again shortly.');
      inFlight++;
      const delivery = { fingerprint, pending: true, expires: time + 60 * 60_000 };
      delivery.promise = Promise.resolve().then(() => sendMessage(data));
      deliveries.set(data.requestId, delivery);
      try {
        await delivery.promise;
        delivery.pending = false;
        return reply(res, 200, { ok: true });
      } catch {
        deliveries.delete(data.requestId);
        throw problem(502, 'Delivery could not be confirmed. Please connect on LinkedIn if you need to follow up.');
      } finally { inFlight--; }
    } catch (error) {
      reply(res, error.status || 500, { error: error.status ? error.message : 'Something went wrong. Please try again later.' });
    }
  };
}
