import { readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';

const mode = process.argv[2];
const mappings = {
  api: {
    DATABASE_URL: 'rakazo_database_url', ENCRYPTION_KEY: 'rakazo_encryption_key',
    BETTER_AUTH_SECRET: 'rakazo_auth_secret', SCREEN_PROXY_SECRET: 'rakazo_screen_secret',
    OIDC_CLIENT_SECRET: 'rakazo_oidc_secret', SIGNUP_ALLOWLIST: 'rakazo_owner_email',
  },
  web: { SCREEN_PROXY_SECRET: 'rakazo_screen_secret' },
};
if (!Object.hasOwn(mappings, mode)) throw new Error('Unknown Rakazo process role');
for (const [name, file] of Object.entries(mappings[mode])) {
  const value = readFileSync('/run/secrets/' + file, 'utf8').trim();
  if (!value || /[\r\n\0]/.test(value)) throw new Error('Invalid private Rakazo setting: ' + name);
  process.env[name] = value;
}
// This release cannot be switched into an inference deployment by a service override.
if (mode === 'api') {
  process.env.WORKSPACE_ONLY = 'true';
  process.env.SANDBOX_PROVIDER = 'none';
  process.env.CLOUD_AGENT_PROVIDER = 'none';
  process.env.AUTH_PASSWORD_ENABLED = 'false';
  process.env.OIDC_ALLOW_SIGNUP_BYPASS = 'false';
}
const args = mode === 'api'
  ? ['--enable-source-maps', 'dist/index.js']
  : ['node_modules/vite/bin/vite.js', 'preview', '--host', '0.0.0.0', '--port', '5173'];
const child = spawn(process.execPath, args, { cwd: '/app/apps/' + (mode === 'api' ? 'api' : 'web'), stdio: 'inherit', env: process.env });
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => child.kill(signal));
child.on('error', () => { console.error('Rakazo process could not start'); process.exitCode = 1; });
child.on('exit', (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0); });
