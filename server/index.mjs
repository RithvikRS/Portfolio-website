import { createPortfolioServer } from './app.mjs';
import { createMailer } from './mailer.mjs';

const port = Number(process.env.PORT || 4173);
const host = process.env.HOST || '127.0.0.1';
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid PORT.');
if (process.env.NODE_ENV === 'production' && !process.env.PUBLIC_ORIGIN) throw new Error('Set PUBLIC_ORIGIN to the public HTTPS origin.');
const url = new URL(process.env.PUBLIC_ORIGIN || `http://127.0.0.1:${port}`);
if (process.env.NODE_ENV === 'production' && url.protocol !== 'https:') throw new Error('Production PUBLIC_ORIGIN must use HTTPS.');
const sendMessage = createMailer();
const trustedProxyIPs = (process.env.TRUSTED_PROXY_IPS || '').split(',').map(ip => ip.trim()).filter(Boolean);
const server = await createPortfolioServer({ origin: url.origin, sendMessage, trustProxy: process.env.TRUST_PROXY === 'true', trustedProxyIPs, adminEnabled: process.env.ADMIN_ENABLED === 'true', adminUsername: process.env.ADMIN_USERNAME || 'rithvik' });
server.listen(port, host, () => {
  console.log(`Portfolio: http://${host}:${port}`);
  console.log(sendMessage ? 'SMTP configured; delivery is confirmed per submission.' : 'SMTP is not configured. Contact form will offer LinkedIn instead.');
});
for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => {
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 15_000).unref();
});
