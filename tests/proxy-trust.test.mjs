import test from 'node:test';
import assert from 'node:assert/strict';
import { proxyMatcher } from '../server/proxy-trust.mjs';
import { adminIdentity } from '../server/admin.mjs';

test('private overlay CIDR trusts only its range, including mapped IPv4', () => {
  const match = proxyMatcher(['10.42.0.0/24']);
  for (const ip of ['10.42.0.2', '10.42.0.254', '::ffff:10.42.0.7']) assert.equal(match(ip), true);
  for (const ip of ['10.42.1.2', '10.0.0.13', '127.0.0.1', '203.0.113.1', 'bad', undefined]) assert.equal(match(ip), false);
});
test('invalid and all-address trust configurations fail closed', () => {
  for (const entry of ['0.0.0.0/0', '::/0', '10.42.0.0/33', '10.42.0.0/', '10.42.0.0/-1', 'bad', '10.42.0.0/24/x']) assert.throws(() => proxyMatcher([entry]));
});
test('Swarm identity still requires the trusted peer, username and admin group', () => {
  const options = { enabled: true, trustedProxyIPs: ['10.42.0.0/24'], username: 'rithvik' };
  const headers = { 'remote-user': 'rithvik', 'remote-groups': 'admins' };
  const req = peer => ({ socket: { remoteAddress: peer }, headers });
  assert.ok(adminIdentity(req('10.42.0.5'), options));
  assert.equal(adminIdentity(req('10.0.0.13'), options), null);
  assert.equal(adminIdentity({ ...req('10.42.0.5'), headers: {} }, options), null);
});
