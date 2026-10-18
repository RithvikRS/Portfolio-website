import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createNotesStore } from '../server/notes-store.mjs';
import { renderMarkdown } from '../server/notes.mjs';
import { createPortfolioServer } from '../server/app.mjs';

const draft = { kind: 'note', title: 'Learning Docker', summary: 'Notes on containers', tags: ['Docker'], body: '## Containers\n\nPrivate learning content.' };
async function directory(t) { const path = await mkdtemp(join(tmpdir(), 'fieldnotes-')); t.after(() => rm(path, { recursive: true, force: true })); return path; }
test('drafts, published snapshots, conflicts, trash and restart preserve visibility', async t => {
  const path = await directory(t); const store = await createNotesStore(path);
  let entry = await store.create(draft);
  assert.equal(store.published('note').length, 0);
  entry = await store.change(entry.id, 'publish', { revision: entry.revision });
  const original = entry.published.body;
  const results = await Promise.allSettled([store.change(entry.id, 'save', { ...draft, body: 'New private version', revision: entry.revision }), store.change(entry.id, 'save', { ...draft, body: 'Conflicting text', revision: entry.revision })]);
  assert.equal(results.filter(result => result.status === 'fulfilled').length, 1);
  assert.equal(results.find(result => result.status === 'rejected').reason.status, 409);
  assert.equal(store.published('note')[0].published.body, original);
  let restarted = await createNotesStore(path);
  entry = restarted.get(entry.id);
  assert.equal(entry.draft.body, 'New private version'); assert.equal(entry.published.body, original);
  entry = await restarted.change(entry.id, 'publish', { revision: entry.revision });
  assert.equal(restarted.published('note')[0].published.body, 'New private version');
  entry = await restarted.change(entry.id, 'trash', { revision: entry.revision });
  assert.equal(restarted.published('note').length, 0);
  await assert.rejects(restarted.change(entry.id, 'publish', { revision: entry.revision }), { status: 409 });
  entry = await restarted.change(entry.id, 'restore', { revision: entry.revision });
  assert.equal(entry.published, null); assert.equal(entry.deletedAt, null);
  assert.equal(restarted.export().entries[0].draft.body, 'New private version');
  assert.equal((await readdir(path)).length, 1);
  assert.equal(JSON.parse(await readFile(join(path, `${entry.id}.json`))).revision, entry.revision);
  await assert.rejects(restarted.create({ ...draft, body: 'x'.repeat(65537) }), { status: 400 });
  await assert.rejects(restarted.create({ ...draft, tags: ['x'.repeat(33)] }), { status: 400 });
});
test('Markdown allows formatting and code while stripping executable content', () => {
  const html = renderMarkdown('# Heading\n\n**Bold**\n\n```js\n<script>alert(1)</script>\n```\n\n<script>alert(2)</script><img src=x onerror=alert(3)><iframe src="https://evil.test"></iframe><svg><a onload=alert(4)>x</a></svg>\n\n[bad](javascript:alert)\n\n[good](https://example.com)\n\n- [x] Done');
  assert.match(html, /<h1>Heading<\/h1>/); assert.match(html, /<strong>Bold<\/strong>/); assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script|<img|<iframe|<svg|onerror|onload|href="javascript:/);
  assert.match(html, /href="https:\/\/example.com"/); assert.match(html, /type="checkbox" disabled/);
  assert.doesNotMatch(renderMarkdown('<a href="//evil.test">x</a><style>body{display:none}</style><input type="password" autofocus>'), /href=|<style|type="password"|autofocus/);
});
async function fixture(t, overrides = {}) {
  const path = await directory(t);
  const origin = 'https://writing.example';
  const server = await createPortfolioServer({ notesDirectory: path, origin, adminEnabled: true, trustProxy: true, trustedProxyIPs: ['127.0.0.1'], ...overrides });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const headers = { 'remote-user': 'rithvik', 'remote-groups': 'admins', Origin: origin, 'X-Requested-With': 'fieldnotes', 'Content-Type': 'application/json' };
  const request = (url, options = {}) => fetch(`http://127.0.0.1:${server.address().port}${url}`, options);
  const api = async (url, body, extra = {}) => request(`/admin/notes/api/${url}`, { method: body ? 'POST' : 'GET', headers, ...(body ? { body: JSON.stringify(body) } : {}), ...extra });
  return { request, api, headers };
}
test('HTTP authorization, CSRF, publication isolation, search, export and unpublish', async t => {
  const { request, api, headers } = await fixture(t);
  assert.equal((await request('/admin/notes/')).status, 401);
  assert.equal((await request('/admin/notes/api/export')).status, 401);
  assert.equal((await request('/admin/notes/api/entries', { headers: { ...headers, 'remote-groups': 'users' } })).status, 401);
  const editor = await request('/admin/notes/', { headers }); assert.equal(editor.status, 200); assert.match(await editor.text(), /Make room for/);
  for (const override of [{ Origin: 'https://evil.test' }, { Origin: '' }, { 'X-Requested-With': '' }, { 'Sec-Fetch-Site': 'cross-site' }]) {
    assert.equal((await api('entries', draft, { headers: { ...headers, ...override } })).status, 403);
  }
  let response = await api('entries', draft); assert.equal(response.status, 201); let entry = await response.json();
  const url = `/learn/${entry.slug}/`;
  assert.equal((await request(url)).status, 404);
  assert.doesNotMatch(await (await request('/learn/?q=Private')).text(), /Learning Docker/);
  assert.equal((await request(`/.notes/${entry.id}.json`)).status, 404);
  response = await api(`entries/${entry.id}/publish`, { revision: entry.revision }); entry = await response.json();
  response = await request(url); assert.equal(response.status, 200); assert.equal(response.headers.get('cache-control'), 'no-store'); assert.match(await response.text(), /Private learning content/);
  entry = await (await api(`entries/${entry.id}/save`, { ...draft, title: '<img src=x onerror=alert(1)>', body: 'Secret draft revision', revision: entry.revision })).json();
  assert.doesNotMatch(await (await request(url)).text(), /Secret draft/);
  assert.doesNotMatch(await (await request('/learn/?q=Secret')).text(), /Learning Docker/);
  const backup = await api('export'); assert.match(backup.headers.get('content-disposition'), /attachment/); assert.equal((await backup.json()).entries.length, 1);
  assert.equal((await request(url, { method: 'HEAD' })).status, 200);
  assert.equal((await request(url, { method: 'POST' })).status, 405);
  entry = await (await api(`entries/${entry.id}/unpublish`, { revision: entry.revision })).json();
  assert.equal((await request(url)).status, 404);
  assert.equal((await api('entries', { ...draft, kind: 'invalid' })).status, 400);
  assert.equal((await api(`entries/${entry.id}/save`, { ...draft, revision: 1 })).status, 409);
});
test('untrusted peers cannot read writing even with forged identity headers', async t => {
  const { request, headers } = await fixture(t, { trustedProxyIPs: ['172.30.0.3'] });
  assert.equal((await request('/admin/notes/api/entries', { headers })).status, 401);
});
