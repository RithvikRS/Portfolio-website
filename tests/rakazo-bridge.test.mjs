import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {pilotAssets} from '../deploy/rakazo/bridge.mjs';

async function browser(basePath) {
  const {page, js} = pilotAssets(basePath);
  const elements = Object.fromEntries(['status', 'screen', 'start', 'view', 'control', 'stop'].map(id => [id, {id}]));
  const requests = [];
  let refresh;
  vm.runInNewContext(js, {
    document: {
      querySelector: selector => elements[selector.slice(1)],
      querySelectorAll: () => ['start', 'view', 'control', 'stop'].map(id => elements[id]),
    },
    fetch: async (url, options) => {
      requests.push({url, method: options?.method ?? 'GET'});
      return {ok: true, json: async () => ({running: true, message: 'Ready'})};
    },
    setInterval: fn => {refresh = fn;},
  });
  await new Promise(resolve => setImmediate(resolve));
  return {page, elements, requests, refresh};
}

for (const prefix of ['', '/computer']) {
  test(`pilot controls and refresh retain the ${prefix || 'root'} prefix`, async () => {
    const {page, elements, requests, refresh} = await browser(prefix);
    assert.ok(page.includes(`src="${prefix}/pilot.js"`));
    assert.deepEqual(requests, [{url: prefix + '/api/status', method: 'GET'}]);
    await elements.start.onclick();
    await elements.view.onclick();
    assert.equal(elements.screen.src, prefix + '/desktop/embed.html?view_only=1');
    await elements.control.onclick();
    assert.equal(elements.screen.src, prefix + '/desktop/embed.html?view_only=0');
    refresh();
    await new Promise(resolve => setImmediate(resolve));
    await elements.stop.onclick();
    assert.deepEqual(requests.slice(1).map(r => r.url), ['start', 'view', 'control', 'control', 'stop'].map(name => prefix + '/api/' + name));
    assert.ok(requests.slice(1).every(r => r.method === 'POST'));
    assert.equal(elements.screen.src, 'about:blank');
    assert.equal(elements.screen.hidden, true);
    const count = requests.length;
    refresh();
    assert.equal(requests.length, count);
  });
}

test('base path rejects external, ambiguous and injectable locations', () => {
  for (const path of ['/', '/computer/', '//evil.test', 'https://evil.test', '/a/../b', '/a?x=1', '/a#b', '/a%2fb', '/a\\b', '/a"', null, 1, '/' + 'a'.repeat(128)]) {
    assert.throws(() => pilotAssets(path), /BASE_PATH/);
  }
  assert.ok(pilotAssets('/workspace/computer').page.includes('/workspace/computer/pilot.js'));
});
