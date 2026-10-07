# Admin dashboard and shared login

Stage 1 was deployed on **8 October 2026 (Asia/Kolkata)**. The dashboard is served by the portfolio app. Authelia v4.39.28 handles login; its container image is pinned by digest in `compose.production.yaml`. Caddy checks the session before forwarding administrator requests.

## What is available

| Stage | Scope | Status |
| --- | --- | --- |
| 1 | Admin dashboard, Authelia username/password login, HTTPS | Deployed |
| 2 | Portainer with shared login | Awaiting user approval; not installed |
| 3 | Blog and learning notebook, browser editor | Awaiting separate approval; not implemented |

The dashboard shows a working portfolio link and inactive cards for the next stages. A shared sign-in service is in place, but no Portainer or blog authentication client is configured yet. Approve and verify each stage before starting the next.

## Sign in

1. Open [the admin dashboard](https://rithvik.ddns.net/admin/).
2. Caddy redirects signed-out visitors to [Authelia](https://rithvik.ddns.net/auth/).
3. Sign in as `rithvik` with the generated password. Authelia returns you to `/admin/`.
4. Use **Sign out** in the dashboard to end the current shared-login session.

The initial password is in `Portfolio admin login.txt`, saved privately beside the Oracle SSH key on the development computer. The server copy is `/opt/portfolio/.auth/bootstrap-login.txt`, readable only by its owner. Save the password in your password manager. Neither the password nor session cookie belongs in repository documentation, shell history, or screenshots.

Sessions expire after 30 minutes of inactivity or 8 hours total. Remember-me is disabled. Restarting Authelia invalidates its in-memory sessions; the redeployment script intentionally recreates it. This stage uses one-factor authentication. TOTP, WebAuthn, email password reset, and additional application SSO clients are not configured.

## How requests are protected

```text
Browser -- HTTPS --> Caddy -- session check --> Authelia
                       |
                       +-- verified admin identity --> Node /admin/
                       +-- public request ----------> Node portfolio
```

Only Caddy publishes web ports. App and Authelia listen privately on 4173 and 9091. Auth has a network shared with Caddy, separate from the app backend.

Caddy removes visitor-supplied `Remote-User`, `Remote-Groups`, `Remote-Email`, and `Remote-Name` headers. For `/admin/`, it asks Authelia to verify the session and copies the verified identity. The app also requires `ADMIN_ENABLED=true`, proxy trust, the exact configured proxy peer IP, the configured username, and membership in `admins`. The page is marked `no-store` and `noindex`.

Authelia's default access policy is deny; the configured rule permits the `admins` group on `/admin` and its subpaths after password authentication. Login regulation is configured for five retries within two minutes and a ten-minute ban. A dashboard card alone grants no access to an application.

## Files and ownership

| File or directory | Purpose |
| --- | --- |
| `server/admin.mjs` | Identity check and server-rendered dashboard |
| `css/admin.css` | Desktop and mobile styling |
| `tests/admin.test.mjs` | Trusted proxy, identity, escaping, caching and HTTP checks |
| `deploy/authelia/configuration.yml` | Versioned non-secret auth configuration |
| `deploy/Caddyfile.docker` | Login and dashboard routes; identity-header stripping |
| `scripts/setup-admin.py` | One-time Linux account/key generation |
| `.auth/secrets/users.yml` | Account metadata, Argon2id hash, `admins` group |
| `.auth/secrets/session-secret` | Session secret |
| `.auth/secrets/storage-key` | SQLite encryption key |
| `.auth/data/db.sqlite3` | Persistent auth database |
| `.auth/data/notifications.txt` | Filesystem notifier output, not SMTP delivery |
| `.auth/bootstrap-login.txt` | Initial plaintext credential record |

On Oracle, `.auth/` and its subdirectories have mode 700; secret files have mode 600. They belong to the deployment user. Compose runs Authelia with `AUTHELIA_UID:AUTHELIA_GID`, currently `1000:1000`. The secrets mount is read-only; `.auth/data/` is writable. `.auth/` is ignored by Git, excluded by the Docker build allowlist, and not served by Node.

Keep the storage key with its database. Replacing the key while retaining the database prevents decryption. The setup helper refuses to overwrite `.auth/`; do not remove it to make setup run again.

## First initialization

Already completed on the current Oracle server. On a new Linux checkout, create and configure `.env.production`, then run as the normal deployment user:

```sh
cd /opt/portfolio
python3 scripts/setup-admin.py
bash portfolio_redeploy.sh --no-pull
```

The helper reads `ADMIN_USERNAME`, `DOMAIN`, and the auth user ID from Compose. It generates a random 32-character password and an Argon2id hash without printing either. Python 3 and Docker are required; no Python packages are installed. The display name and email are currently set by this personal setup helper; adapt them if reusing the repository for another owner.

## Password change or recovery

Use SSH if the password is lost or needs changing. Back up the current account file privately first. Generate the replacement hash interactively:

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.production -f compose.production.yaml exec auth \
  authelia crypto hash generate argon2 --parallelism 1
```

Enter the new password at the prompt, not as a command argument. Copy the generated digest, then edit `.auth/secrets/users.yml` with `nano` and replace only the account's quoted `password` hash. Preserve the username and `admins` group. The file is JSON-compatible YAML; keep its syntax valid.

```sh
sudo docker compose --env-file .env.production -f compose.production.yaml restart auth
sudo docker compose --env-file .env.production -f compose.production.yaml ps
```

Sign in with the new password and update your password manager. Restarting invalidates existing sessions. The bootstrap file and its local copy are not updated automatically. There is no email password-reset flow in this stage.

## Backups and recovery data

Preserve `.env.production`, the complete `.auth/` directory, and both Caddy named volumes. Store backups privately outside Git. For a consistent filesystem copy of `.auth/`, briefly stop only `auth`, copy/archive the directory with permissions, and start `auth` again. The portfolio remains available while sign-in is temporarily unavailable. Do not run `down --volumes` as a backup step.

Stage 1 created these private recovery items on Oracle:

- Directory: `/home/opc/.config/portfolio-deploy/admin-stage1-YzXVP4Gu/`.
- `source-before.tar.gz`: source and private environment before stage 1.
- `auth-stage1.tar.gz`: new account, keys, and database, archived while auth was stopped.
- Docker image tag `rithvik-portfolio:before-admin-stage1`: previous app image.

These are deployment-time recovery points, not scheduled backups. The pre-stage-1 source archive does not contain the new auth data. Restore source, Compose/Caddy configuration, and a compatible image together if rolling back; switching an image alone does not undo proxy or auth changes. Preserve current files before restoring. For migration, restore keys and database together, restore ownership for the configured UID/GID, and retain Caddy's certificate volumes.

## Troubleshooting

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.production -f compose.production.yaml ps
sudo docker compose --env-file .env.production -f compose.production.yaml logs --tail=100 auth caddy app
curl -I https://rithvik.ddns.net/admin/
curl https://rithvik.ddns.net/auth/api/health
```

| Symptom | Likely cause or next check |
| --- | --- |
| `/admin/` redirects to `/auth/` | Expected when signed out |
| Logged out after deployment | Expected; auth was recreated and its sessions were in memory |
| Repeated login attempts stop working | Wait for the ban period; confirm credentials and inspect auth logs |
| Credentials accepted but dashboard denied | User must match `ADMIN_USERNAME`, belong to `admins`, and reach Node through trusted Caddy |
| 401 from `localhost:8080/admin/` | Local Compose has no shared-login stack; expected |
| 502 on `/auth/` or `/admin/` | Check auth health, network, mount permissions, and startup logs |
| Auth fails before startup checks | Retain the tested Compose HTTP health check and `server.disable_healthcheck: true`; the latter avoids writing a legacy image file on a read-only filesystem |
| Decryption failure after restoring | Restore the matching storage key and database together |

## Verification record

Stage 1 checks passed on 8 October 2026: 15 automated app tests; production build/link checks; HTTPS redirects to sign-in; successful credential authentication; authenticated dashboard access; session invalidation on sign-out; rejection of forged identity headers and encoded-path access; private-file denial; public pages and contact availability. Desktop and phone layouts were reviewed locally. No Portainer or writing service was installed, and no test email was sent. The in-app browser could not open the live hostname during review; live auth behavior was verified through HTTPS requests.

Further changes should retain these checks and add tests relevant to the new integration. Portainer is the next approval gate; writing tools follow after that stage is accepted.

References: [Authelia with Caddy](https://www.authelia.com/integration/proxies/caddy/), [session configuration](https://www.authelia.com/configuration/session/introduction/), and [private secrets](https://www.authelia.com/configuration/methods/secrets/).
