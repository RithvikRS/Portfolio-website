import test from 'node:test';
import assert from 'node:assert/strict';
import { adminIdentity } from '../server/admin.mjs';
import { createPortfolioServer } from '../server/app.mjs';

const headers = { 'remote-user': 'rithvik', 'remote-groups': 'users,admins', 'remote-name': 'Rithvik' };
const options = { enabled: true, trustedProxyIPs: ['172.30.0.3'], username: 'rithvik' };
const req = (peer, values = headers) => ({ socket: { remoteAddress: peer }, headers: values });

test('only the configured proxy can supply an administrator identity', () => {
  assert.equal(adminIdentity(req('198.51.100.1'), options), null);
  assert.equal(adminIdentity(req('172.30.0.4'), options), null);
  assert.equal(adminIdentity(req('172.30.0.3'), { ...options, enabled: false }), null);
  assert.equal(adminIdentity(req('172.30.0.3', { ...headers, 'remote-user': 'someone-else' }), options), null);
  assert.equal(adminIdentity(req('172.30.0.3', { ...headers, 'remote-groups': 'users' }), options), null);
  assert.equal(adminIdentity(req('172.30.0.3', {}), options), null);
  assert.deepEqual(adminIdentity(req('::ffff:172.30.0.3'), options), { username: 'rithvik', name: 'Rithvik' });
});

async function fixture(t, overrides = {}) {
  const server = await createPortfolioServer({ adminEnabled: true, trustProxy: true, trustedProxyIPs: ['127.0.0.1'], ...overrides });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  return (path = '/admin/', init = {}) => fetch(`http://127.0.0.1:${server.address().port}${path}`, init);
}

test('dashboard requires authentication, escapes names, and is never cached', async t => {
  const request = await fixture(t);
  assert.equal((await request()).status, 401);
  const response = await request('/admin/', { headers: { ...headers, 'remote-name': '<script>alert(1)</script>' } });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(response.headers.get('x-robots-tag'), 'noindex, nofollow');
  const html = await response.text();
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
  assert.ok(!html.includes('<script>alert(1)</script>'));
  assert.ok(html.includes('href="/portainer/"'));
  assert.ok(!html.includes('href="/learn'));
  const head = await request('/admin', { method: 'HEAD', headers });
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
  assert.equal((await request('/admin/', { method: 'POST', headers })).status, 405);
  assert.equal((await request('/')).status, 200);
});

test('dashboard stays closed when disabled or proxy trust is absent', async t => {
  for (const overrides of [{ adminEnabled: false }, { trustProxy: false }, { trustedProxyIPs: ['172.30.0.3'] }]) {
    const request = await fixture(t, overrides);
    assert.equal((await request('/admin/', { headers })).status, 401);
  }
});
