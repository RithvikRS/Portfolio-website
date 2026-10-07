import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import { createContactHandler } from '../server/contact.mjs';

const origin = 'https://portfolio.example.com';
function fixture(options = {}) {
  const handler = createContactHandler({ origin, sendMessage: async () => {}, requestLimit: 1, ...options });
  return async (peer, forwarded) => {
    const req = Readable.from([Buffer.from(JSON.stringify({ name: 'Alex Morgan', email: 'alex@example.com', subject: '', message: 'A message for the portfolio owner.', requestId: randomUUID() }))]);
    req.method = 'POST';
    req.headers = { origin, 'content-type': 'application/json', 'x-real-ip': forwarded };
    req.socket = { remoteAddress: peer };
    let status;
    await handler(req, { writeHead(value) { status = value; }, setHeader() {}, end() {} });
    return status;
  };
}

test('the configured container proxy preserves per-visitor limits, including mapped IPv4', async () => {
  const post = fixture({ trustProxy: true, trustedProxyIPs: ['172.30.0.3'] });
  assert.equal(await post('172.30.0.3', '198.51.100.1'), 200);
  assert.equal(await post('::ffff:172.30.0.3', '198.51.100.2'), 200);
  assert.equal(await post('172.30.0.3', '::ffff:198.51.100.1'), 429);
});

test('other containers cannot evade limits with forged forwarding headers', async () => {
  const post = fixture({ trustProxy: true, trustedProxyIPs: ['172.30.0.3'] });
  assert.equal(await post('172.30.0.4', '198.51.100.1'), 200);
  assert.equal(await post('172.30.0.4', '198.51.100.2'), 429);
});

test('disabled proxy trust and invalid forwarded addresses fall back to the peer', async () => {
  const direct = fixture({ trustedProxyIPs: ['172.30.0.3'] });
  assert.equal(await direct('172.30.0.3', '198.51.100.1'), 200);
  assert.equal(await direct('172.30.0.3', '198.51.100.2'), 429);
  const proxied = fixture({ trustProxy: true, trustedProxyIPs: ['172.30.0.3'] });
  assert.equal(await proxied('172.30.0.3', 'invalid'), 200);
  assert.equal(await proxied('172.30.0.3', '198.51.100.1, 198.51.100.2'), 429);
});

test('proxy configuration rejects wildcards, subnets, and hostnames', () => {
  for (const ip of ['*', '172.30.0.0/24', 'caddy', 'not-an-ip']) {
    assert.throws(() => fixture({ trustProxy: true, trustedProxyIPs: [ip] }), /TRUSTED_PROXY_IPS/);
  }
});
