# Portainer on Oracle

Stage 2 was deployed on **8 October 2026 (Asia/Kolkata)**. Portainer CE **2.45.2 LTS** is pinned by image digest in `compose.production.yaml`. The dashboard links to it at [https://rithvik.ddns.net/portainer/](https://rithvik.ddns.net/portainer/). Blog and learning-note editing remain pending separate approval.

## Sign in and sign out

Open the [dashboard](https://rithvik.ddns.net/admin/), sign in with the existing `rithvik` Authelia account, and select **Open Portainer**. You can also open Portainer directly. If Portainer shows its login screen, choose **Login with OAuth**; the existing Authelia session supplies the identity without another password. The **Oracle Docker** environment is already connected.

The normal account has Portainer administrator access. It can manage all containers, inspect logs, open consoles, and change volumes, images, and networks. Docker socket access gives it control of the Oracle host's containers. Use the repository and `portfolio_redeploy.sh` for the portfolio stack's lasting configuration; changes made directly in Portainer can be replaced by the next Compose deployment. An externally created Compose stack can appear with limited stack editing in Portainer while its containers remain manageable.

Authelia expires sessions after 30 minutes of inactivity or eight hours total. Portainer maintains its own eight-hour session. Caddy checks the shared session on every new HTTP request under `/portainer/`, so a Portainer token alone cannot bypass shared login. The **Portainer logout** action clears its session and sends you to Authelia logout. Dashboard **Sign out** ends the Authelia session and blocks subsequent private requests, but does not itself revoke Portainer's token. Already-open WebSocket console connections can remain until closed; close consoles when signing out. This is shared sign-in with a proxy gate, not universal OIDC back-channel logout.

## How SSO and routing work

```text
Browser -> HTTPS Caddy -> Authelia session/group check
                         |
                         +-> strip /portainer -> portainer:9000

Portainer OAuth -> Authelia /auth/api/oidc/authorization
               -> code exchange + user info -> rithvik (administrator)
```

- `/portainer` redirects to `/portainer/` so relative assets resolve correctly.
- Portainer runs with `--base-url=/portainer`. Caddy checks the original path before stripping the prefix. The explicit `route` preserves that ordering.
- Portainer 2.45 requests translation JSON at `/locales/*/translation.json` despite its base URL. Caddy redirects those requests to the corresponding protected `/portainer/locales/` path so labels render. Keep that root namespace reserved until Portainer supports its base URL for translations.
- Authelia's OIDC client `portfolio-portainer` restricts authorization to `admins`. Its callback is exactly `https://rithvik.ddns.net/portainer/`.
- The client uses authorization-code flow and a secret, with `preferred_username` mapping to the pre-created Portainer user. Automatic account provisioning is disabled. New Authelia users do not automatically become Portainer administrators.
- Caddy, Portainer, and Authelia use private Docker networks. Portainer has no host port mappings; do not open 8000, 9000, or 9443 in Oracle ingress rules. The Docker socket is local, not exposed as a public TCP API.
- `management` connects Caddy and Portainer; `identity` connects Caddy and Authelia; `backend` connects Caddy and Node. Portainer is not attached to the app's trusted backend network.

## Files and redeployment

| Location | Purpose |
| --- | --- |
| `compose.production.yaml` | Portainer service, pinned image, base URL, private network, socket and data mounts |
| `deploy/Caddyfile.docker` | Protected Portainer route and prefix handling |
| `deploy/authelia/configuration.yml` | OIDC provider, administrator policy, client and callback |
| `scripts/setup-portainer.py` | Idempotent key preparation and API configuration |
| `.auth/secrets/oidc-hmac` | OIDC signing secret |
| `.auth/secrets/oidc-private.pem` | RSA token signing key |
| `.auth/secrets/portainer-client-hash` | PBKDF2 hash of the client secret |
| `.portainer/oauth-client.json` | Matching raw client secret and digest, private to deployment |
| `.portainer/recovery-password` | Initial Portainer `admin` recovery password |
| `.portainer/data/` | Persistent Portainer database, user roles, settings and environment |

The `.portainer/` parent is mode 700 and credential files are mode 600, owned by `opc`. Portainer runs as root and owns its database files, so backups need `sudo`. Both private directories are ignored by Git and excluded from the app image. Do not delete them to reset a failed deployment.

After committing, merging into `main`, and pushing, run inside SSH:

```sh
bash /opt/portfolio_redeploy.sh
```

The script calls `--prepare` before validating Authelia, starts Portainer, calls `--configure` before the final Caddy update, and verifies signed-out access. Repeated setup preserves passwords, keys, user IDs, and the existing environment. It uses the private Docker API address and never prints credentials. It stops rather than replacing inconsistent or missing credentials for an existing database. Do not manually rotate the client secret without updating its matching Authelia hash and Portainer settings together.

For a domain move, set `DOMAIN` in the server's `.env.production` after configuring DNS, then run `bash /opt/portfolio_redeploy.sh --no-pull`. This updates Caddy, Authelia's callback, Portainer's trusted origin, and its OAuth endpoint URLs. The username must still match the existing Authelia account. See [the Docker guide](DOCKER.md#changing-the-domain).

## Recovery access

The separate initial Portainer account is `admin`. Its generated password is in `/opt/portfolio/.portainer/recovery-password` and the private local `Portainer recovery login.txt` beside the Oracle SSH key. Use `rithvik` with OAuth for ordinary access. The recovery account remains available to the redeploy helper even when OAuth is enabled.

If the shared-login service is broken, keep public protections in place and use an SSH tunnel. In Oracle SSH, get the current container address (it can change):

```sh
sudo docker inspect portfolio-portainer-1 \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

On your computer, replace `CONTAINER_IP` below with that result and use the full key path for this computer:

```powershell
ssh -i "C:\Users\rithv\OneDrive\Desktop\Development\Oracle Cloud\micro-amd-ssh-key-2026-10-04.key" `
  -L "127.0.0.1:19000:CONTAINER_IP:9000" opc@144.24.135.201
```

Keep the SSH window open. This forwards only localhost. The recovery API is `http://127.0.0.1:19000/api`; a browser may not work normally there because production enforces secure cookies and its HTTPS origin. Prefer diagnosing through SSH and restoring matching configuration. The setup helper authenticates directly to the private API with the initial account; after repairs, rerun `python3 scripts/setup-portainer.py --configure`. Do not disable Authelia or publish Portainer's ports to fix login.

If the `admin` password is intentionally changed through Portainer, update the private recovery-password file to match before redeploying; the CLI file does not reset an existing database password. Update the local recovery record too. Otherwise API reconciliation will stop with an authentication error.

## Backup and restore

Preserve `.env.production`, all of `.auth/`, all of `.portainer/`, the corresponding source version, and Caddy's certificate volumes. The Portainer database contains authentication configuration and must be kept private. For a consistent private-state archive, run in Oracle SSH:

```sh
cd /opt/portfolio
umask 077
backup=$(mktemp -d /home/opc/.config/portfolio-deploy/private-state-XXXXXXXX)
dc() { sudo docker compose --env-file .env.production -f compose.production.yaml "$@"; }
dc stop auth portainer
sudo tar -czf "$backup/private-state.tar.gz" .env.production .auth .portainer
sudo chmod 600 "$backup/private-state.tar.gz"
dc start auth portainer
dc ps
```

If archiving fails, start both services again before troubleshooting. Public portfolio pages remain available during this brief pause. This archive does not include Caddy's named volumes; back those up separately for a full migration. Restore the matched directories while their services are stopped, preserve owners/modes, and use the compatible source and image version. Never restore an old Authelia encryption key over a newer database without its matching backup.

The deployment recovery directory is `/home/opc/.config/portfolio-deploy/portainer-stage2-6erYb3rT/`. It contains the pre-stage-2 source/private configuration archive and a SQLite backup of the earlier auth database. The previous app image is `rithvik-portfolio:before-portainer-stage2`. The post-deployment private-state backup in the same directory preserves the completed integration. These are manual recovery points, not scheduled backups.

## Checks and troubleshooting

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.production -f compose.production.yaml ps
sudo docker compose --env-file .env.production -f compose.production.yaml logs --tail=80 portainer auth
curl -I https://rithvik.ddns.net/portainer/
python3 scripts/setup-portainer.py --configure
```

| Symptom | Check |
| --- | --- |
| Signed-out request redirects to Authelia | Expected |
| Portainer presents its own login page | Choose Login with OAuth; the existing shared session is reused |
| OAuth callback fails | Exact callback including trailing slash; matching secret/hash; public Authelia endpoints reachable from Portainer |
| Account not created beforehand | Check the configured `ADMIN_USERNAME` and run the helper; automatic provisioning is deliberately off |
| Origin invalid | `DOMAIN`, Portainer trusted origin, and browser hostname must agree |
| Blank UI or asset errors | Keep `/portainer/`, `--base-url=/portainer`, and Caddy prefix stripping together |
| Oracle environment unavailable | Portainer logs, Docker service, socket mount and permissions |
| Setup returns 422 | Recovery password must match initial `admin`; changing its file alone cannot reset an existing password |
| Memory pressure on the micro instance | Inspect `docker stats --no-stream`; avoid simultaneous builds/heavy tools |

Verified at deployment: 15 app tests; production build and link checks; configuration validation; repeated helper execution; one shared login followed by a successful OAuth exchange as `rithvik` with administrator role; four running containers readable through the public protected API and browser UI; Portainer assets and translation labels; signed-out/forged-header rejection; shared sign-out protection; private-file denial; and unchanged public/contact health. No email was sent. The writing service remains unimplemented.

References: [Authelia Portainer integration](https://www.authelia.com/integration/openid-connect/clients/portainer/), [Portainer OAuth settings](https://docs.portainer.io/admin/settings/authentication/oauth), [Portainer CLI options](https://docs.portainer.io/advanced/cli).
