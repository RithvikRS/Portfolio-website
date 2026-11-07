// Run inside an isolated container, before attaching the production service.
// Credentials arrive via a private, temporary JSON file; never print API bodies.
import fs from 'node:fs';
const privatePath = '/app/data/.portfolio-bootstrap.json';
const input = JSON.parse(fs.readFileSync(privatePath, 'utf8'));
const base = 'http://127.0.0.1:20128';
let cookie = '';
async function request(path, body) {
  const response = await fetch(base + path, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', Cookie: cookie },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000), redirect: 'manual',
  });
  if (response.headers.get('set-cookie')) cookie = response.headers.get('set-cookie').split(';')[0];
  if (!response.ok) throw new Error(`Bootstrap ${path}: HTTP ${response.status}`);
  return response;
}
await request('/api/auth/login', { password: input.bootstrap_password });
const settings = {
  currentPassword: input.bootstrap_password,
  requireLogin: true, oidcEnabled: true, oidcDisablePasswordLogin: true,
  oidcIssuer: 'https://rithvik.ddns.net/auth',
  oidcClientId: 'portfolio-omniroute', oidcClientSecret: input.omniroute.password,
  oidcScopes: ['openid', 'profile', 'email', 'groups'],
  oidcRedirectPath: '/api/auth/oidc/callback',
  oidcAllowedSubjects: ['rithvik.stuff@gmail.com'],
  hidePaidModels: true, freeAccessPolicy: 'strict', excludeTosAvoid: true,
  hideAutoCombos: true, exposeCombosOnly: true,
  cloudEnabled: false, mcpEnabled: false, a2aEnabled: false,
  debugMode: false, logToolSources: false,
};
const response = await fetch(base + '/api/settings', {
  method: 'PATCH', headers: { 'Content-Type': 'application/json', Cookie: cookie },
  body: JSON.stringify(settings), signal: AbortSignal.timeout(30000),
});
if (!response.ok) throw new Error(`Bootstrap settings: HTTP ${response.status}`);
const saved = await response.json();
for (const key of ['requireLogin','oidcEnabled','oidcDisablePasswordLogin','hidePaidModels','freeAccessPolicy','exposeCombosOnly']) {
  if (saved[key] !== settings[key]) throw new Error(`Bootstrap did not persist ${key}`);
}
fs.writeFileSync('/app/data/.portfolio-bootstrap-complete', 'OmniRoute 3.8.53; native OIDC; free-only staging policy\n', { mode: 0o600 });
console.log('Native OIDC and initial free-only policy saved. No provider or application keys created.');
