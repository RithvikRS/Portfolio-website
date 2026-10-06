import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { createPortfolioServer } from '../server/app.mjs';
import { createMailer } from '../server/mailer.mjs';

const origin = 'https://portfolio.example.com';
const message = (overrides = {}) => ({ name: 'Alex Morgan', email: 'alex@example.com', subject: 'Engineering role', message: 'I would like to discuss an engineering opportunity.', website: '', requestId: randomUUID(), ...overrides });
async function fixture(t, options = {}) {
  const deliveries = [];
  const server = await createPortfolioServer({ origin, sendMessage: async data => { deliveries.push(data); }, ...options });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); }));
  const base = `http://127.0.0.1:${server.address().port}`;
  const post = (data = message(), headers = {}) => fetch(`${base}/api/contact`, { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json', ...headers }, body: typeof data === 'string' ? data : JSON.stringify(data) });
  return { base, post, deliveries };
}

test('only SMTP acceptance yields success; repeat submissions send once', async t => {
  const { base, post, deliveries } = await fixture(t);
  assert.deepEqual(await (await fetch(`${base}/api/contact`)).json(), { available: true });
  const payload = message({ name: '  Alex Morgan  ' });
  const responses = await Promise.all([post(payload), post(payload)]);
  for (const response of responses) {
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { ok: true });
  }
  assert.equal(deliveries.length, 1);
  assert.equal(deliveries[0].name, 'Alex Morgan');
  assert.equal((await post({ ...payload, message: 'A different message with the same request id.' })).status, 409);
});

test('unconfigured mailer and failed delivery never report success', async t => {
  const unavailable = await fixture(t, { sendMessage: undefined });
  assert.deepEqual(await (await fetch(`${unavailable.base}/api/contact`)).json(), { available: false });
  assert.equal((await unavailable.post()).status, 503);
  const failed = await fixture(t, { sendMessage: async () => { throw new Error('private SMTP detail'); } });
  const payload = message();
  const responses = await Promise.all([failed.post(payload), failed.post(payload)]);
  for (const response of responses) {
    assert.equal(response.status, 502);
    const body = await response.json();
    assert.equal(body.ok, undefined);
    assert.doesNotMatch(JSON.stringify(body), /private SMTP detail/);
  }
});

test('invalid and abusive requests are rejected before email delivery', async t => {
  const { base, post, deliveries } = await fixture(t, { requestLimit: 100 });
  assert.equal((await post(message(), { Origin: 'https://another.example.com' })).status, 403);
  assert.equal((await post(message(), { Origin: '' })).status, 403);
  assert.equal((await post(message(), { 'Content-Type': 'text/plain' })).status, 415);
  assert.equal((await post('{invalid')).status, 400);
  for (const invalid of [null, [], message({ email: 'bad-address' }), message({ email: 'alex@example.com\r\nBcc: spam@example.com' }), message({ subject: 'Hello\nBcc: spam@example.com' }), message({ name: '' }), message({ message: 'short' }), message({ message: 'x'.repeat(5001) }), message({ website: 'https://spam.example.com' }), message({ requestId: 'invalid' })]) {
    assert.equal((await post(invalid)).status, 400);
  }
  assert.equal((await post('x'.repeat(33 * 1024))).status, 413);
  assert.equal((await fetch(`${base}/api/contact`, { method: 'DELETE' })).status, 405);
  assert.equal(deliveries.length, 0);
});

test('rate limits apply even when clients spoof forwarding headers', async t => {
  const { post, deliveries } = await fixture(t, { requestLimit: 2 });
  assert.equal((await post(message(), { 'X-Real-IP': '198.51.100.1' })).status, 200);
  assert.equal((await post(message(), { 'X-Real-IP': '198.51.100.2' })).status, 200);
  const limited = await post(message(), { 'X-Real-IP': '198.51.100.3' });
  assert.equal(limited.status, 429);
  assert.ok(Number(limited.headers.get('retry-after')) > 0);
  assert.equal(deliveries.length, 2);
});

test('explicit loopback proxy trust preserves separate visitor limits', async t => {
  const { post } = await fixture(t, { requestLimit: 1, trustProxy: true });
  assert.equal((await post(message(), { 'X-Real-IP': '198.51.100.1' })).status, 200);
  assert.equal((await post(message(), { 'X-Real-IP': '198.51.100.2' })).status, 200);
  assert.equal((await post(message(), { 'X-Real-IP': '198.51.100.1' })).status, 429);
});

test('simultaneous SMTP work is bounded', async t => {
  const releases = [];
  const { post } = await fixture(t, { requestLimit: 100, sendMessage: () => new Promise(resolve => releases.push(resolve)) });
  const pending = [];
  try {
    for (let i = 0; i < 3; i++) pending.push(post());
    for (let i = 0; i < 100 && releases.length < 3; i++) await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(releases.length, 3);
    assert.equal((await post()).status, 503);
  } finally {
    releases.forEach(resolve => resolve());
    const responses = await Promise.all(pending);
    responses.forEach(response => assert.equal(response.status, 200));
  }
});

test('public server serves the site and CV but excludes private/source files', async t => {
  const { base } = await fixture(t);
  for (const path of ['/', '/Projects.html', '/Awards.html', '/css/site.css', '/js/site.js', '/images/favicon.svg']) {
    const response = await fetch(`${base}${path}`);
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  }
  const cv = await fetch(`${base}/documents/Rithvik_CV.pdf`);
  assert.equal(cv.status, 200);
  assert.equal(Buffer.from(await cv.arrayBuffer()).subarray(0, 5).toString(), '%PDF-');
  for (const path of ['/.env', '/.env.example', '/.git/config', '/server/index.mjs', '/data/portfolio.json', '/package.json', '/deploy/README.md', '/not/a/page', '/%2e%2e/server/app.mjs']) {
    const response = await fetch(`${base}${path}`);
    assert.equal(response.status, 404, path);
    assert.match(await response.text(), /<base href="\/">/);
  }
  const head = await fetch(`${base}/`, { method: 'HEAD' });
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
});

test('SMTP envelopes use a fixed recipient and verified sender, with visitor Reply-To', async () => {
  const env = { SMTP_HOST: 'smtp.example.com', SMTP_USER: 'account', SMTP_PASS: 'test-only', CONTACT_FROM: 'sender@example.com', CONTACT_TO: 'owner@example.com' };
  let options;
  let envelope;
  const send = createMailer(env, config => {
    options = config;
    return { sendMail: async mail => { envelope = mail; return { accepted: ['owner@example.com'] }; } };
  });
  await send(message({ to: 'attacker@example.com', message: '<script>hello</script>\nSecond line.' }));
  assert.equal(envelope.to, 'owner@example.com');
  assert.equal(envelope.from.address, 'sender@example.com');
  assert.equal(envelope.replyTo.address, 'alex@example.com');
  assert.equal(envelope.html, undefined);
  assert.match(envelope.text, /<script>hello<\/script>/);
  assert.equal(options.requireTLS, true);
  assert.equal(options.secure, false);
  assert.equal(options.tls.rejectUnauthorized, undefined);
  assert.equal(options.disableFileAccess, true);
  assert.equal(options.disableUrlAccess, true);
  const rejected = createMailer(env, () => ({ sendMail: async () => ({ accepted: [] }) }));
  await assert.rejects(rejected(message()), /did not accept/);
  assert.equal(createMailer({}), undefined);
  assert.throws(() => createMailer({ ...env, CONTACT_TO: 'one@example.com,two@example.com' }), /single email/);
  assert.throws(() => createMailer({ ...env, SMTP_PORT: 'invalid' }), /SMTP_PORT/);
  createMailer({ ...env, SMTP_PORT: '465' }, config => { assert.equal(config.secure, true); return {}; });
});
