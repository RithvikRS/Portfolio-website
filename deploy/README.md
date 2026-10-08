# Oracle deployment and alternative host setup

The active Oracle deployment uses Docker Compose at `/opt/portfolio`, with Caddy, the Node app, Authelia, and Portainer. Open the [public site](https://rithvik.ddns.net/) or [admin dashboard](https://rithvik.ddns.net/admin/). For current commands, use the [Docker deployment guide](DOCKER.md); account access and recovery are covered in the [admin guide](ADMIN.md) and [Portainer guide](PORTAINER.md).

The instructions below describe the alternative **systemd deployment for the public portfolio and contact backend**. They use `deploy/portfolio.service` and `deploy/Caddyfile`; production Docker uses `compose.production.yaml` and `deploy/Caddyfile.docker`. Do not start host-based services alongside the Docker stack on the same ports. These host templates do not install Authelia or enable the admin dashboard.

The app can run on an AMD VM and does not depend on Oracle-specific APIs. See Oracle's [Always Free documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) for the service's current conditions.

## Prepare the host

1. Install a supported Node.js release (22.9 or later; Node 24 is suitable), pnpm, and [Caddy using its official instructions](https://caddyserver.com/docs/install).
2. Create an unprivileged `portfolio` system user and group. Copy this project to `/opt/portfolio`, readable by that user. Install packages there with `pnpm install --frozen-lockfile --prod --ignore-scripts`. Do not copy a Windows `node_modules` folder onto Linux.
3. Change `siteUrl` in `data/portfolio.json` to the new public URL, then run `node scripts/build.mjs`, `node scripts/check.mjs`, and `node --test tests/*.test.mjs`. Keep the generated HTML with the source.
4. Copy `.env.example` to `/etc/portfolio.env`, owned by root and readable only by root (`chmod 600 /etc/portfolio.env`). Systemd reads this file before starting the service. Set the values below. Keep credentials out of Git, HTML, and browser JavaScript.

```dotenv
NODE_ENV=production
HOST=127.0.0.1
PORT=4173
PUBLIC_ORIGIN=https://portfolio.example.com
TRUST_PROXY=true
SMTP_HOST=smtp.your-provider.example
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=your-smtp-login
SMTP_PASS=your-provider-app-password
CONTACT_FROM=verified-sender@example.com
CONTACT_TO=your-private-inbox@example.com
```

Replace every example value. `PUBLIC_ORIGIN` must exactly match the browser's origin, including any nonstandard port; use one canonical domain. This setup serves the website at the domain root. Do not put quotes around values unless needed by systemd's environment-file syntax.

`CONTACT_FROM` must be a sender permitted by your provider, usually the authenticated mailbox or a verified domain. `CONTACT_TO` is your destination inbox. The visitor's address becomes **Reply-To**, so replying in your email client reaches them without spoofing their address as the sender. Use your provider's SMTP/app password, not a password stored in the frontend. Set up SPF/DKIM if your provider requires them for a custom domain.

Port 587 uses mandatory STARTTLS; port 465 uses TLS from connection start (`SMTP_SECURE=true`). Certificate verification remains enabled. This uses an existing outbound SMTP provider, not a mail server listening on your VM. Provider quotas and outbound network access still need checking. See [Nodemailer's SMTP documentation](https://nodemailer.com/smtp).

## Start the service and HTTPS proxy

1. Check the Node binary location (`command -v node`) and adjust `ExecStart` in `portfolio.service` if necessary. Copy the unit to `/etc/systemd/system/portfolio.service`. The service account needs read/traverse permission on `/opt/portfolio` and its dependencies.
2. Run `sudo systemctl daemon-reload`, then `sudo systemctl enable --now portfolio`. Inspect `sudo systemctl status portfolio` and `sudo journalctl -u portfolio` if startup fails. The app logs startup status, not message contents or SMTP credentials.
3. Point your domain's DNS to the VM. Replace the example domain in `Caddyfile`, install it as `/etc/caddy/Caddyfile`, validate with `sudo caddy validate --config /etc/caddy/Caddyfile`, and reload Caddy. Its [reverse proxy guide](https://caddyserver.com/docs/quick-starts/reverse-proxy) explains automatic HTTPS.
4. Allow inbound TCP 80 and 443 in both the VM firewall and [Oracle network security rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm). Keep port 4173 private on loopback. Restrict SSH to your administrative access needs. Allow outbound DNS, HTTPS, and the chosen SMTP port.
5. Open the HTTPS website, submit one test message yourself, verify it reaches your inbox (including spam), and test replying. SMTP acceptance does not guarantee inbox placement. Restart `portfolio` after changing environment settings.

The Caddy template replaces `X-Real-IP` with the connected client's IP. Enable `TRUST_PROXY` only with this loopback proxy arrangement. If adding a CDN or load balancer later, revisit client-IP trust and rate limits first.

## Contact behavior and limits

- The form is disabled with a LinkedIn fallback when SMTP configuration is absent. GitHub Pages can still serve the site, but cannot run this Node backend; moving only static HTML there will not activate email delivery.
- Server-side validation, a hidden honeypot, JSON-only requests, and an exact Origin check supplement rate limits. These reduce basic abuse; they do not replace a challenge service if targeted spam becomes a problem.
- Each IP may make five submission attempts per 15 minutes; the process permits 100 attempts per hour overall and three simultaneous SMTP deliveries. A single process is intended. Counters reset on restart and are not shared across replicas.
- Successful submissions are deduplicated by an opaque request ID plus a hashed payload for one hour, within the process. The app does not write messages to disk or log them; memory holds the payload while sending. Your email provider and destination mailbox receive and retain the message.
- A provider timeout can leave delivery uncertain. The form preserves the draft and does not retry automatically. After a restart or an ambiguous SMTP failure, retrying can produce a duplicate email. Use LinkedIn for urgent follow-up.
- The static-file allowlist serves public pages, assets, and the current CV. The separately handled admin route requires a verified identity when enabled. `.env`, `.auth/`, server source, content data, and the old CV are excluded from static serving. A public Git repository and downloadable CV can still expose contact details independently of the website; review those separately before publishing.
