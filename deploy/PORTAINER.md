# Portainer on Oracle

> Production runs on a three-node Swarm with two AMD nodes and an Ampere A1 worker. Use [SWARM.md](SWARM.md) for deployment, status, rollback, and node placement. Compose/systemd commands below apply only to their named legacy or local setup; do not start them alongside production Swarm.

Open [Portainer](https://rithvik.ddns.net/portainer/) to manage the three-node cluster through the **Oracle Swarm** environment. Keep Portainer CE **2.45.2 LTS** pinned by image digest in `compose.production.yaml` until you choose to upgrade. Use [Fieldnotes](FIELDNOTES.md) to edit blog posts and learning notes with the same login.

## Sign in and sign out

Open the [dashboard](https://rithvik.ddns.net/admin/), sign in with the `rithvik` Authelia account, and select **Open Portainer**. You can also open Portainer directly. If Portainer shows its login screen, choose **Login with OAuth** to reuse your shared session. Select **Oracle Swarm** to manage services and nodes across the cluster.

The normal account has Portainer administrator access. It can manage all containers, inspect logs, open consoles, and change volumes, images, and networks. Docker socket access gives it control of the Oracle host's containers. Use the repository and `portfolio_redeploy.sh` for the portfolio stack's lasting configuration; changes made directly in Portainer can be replaced by the next Swarm deployment. Keep persistent changes in the repository service catalog.

Authelia expires sessions after 30 minutes of inactivity or eight hours total. Portainer maintains its own eight-hour session. Caddy checks the shared session on every new HTTP request under `/portainer/`, so a Portainer token alone cannot bypass shared login. The **Portainer logout** action clears its session and returns you to your dashboard on Swarm. Dashboard **Sign out** ends the Authelia session and blocks subsequent private requests, but does not itself revoke Portainer's token. Already-open WebSocket console connections can remain until closed; close consoles when signing out. This is shared sign-in with a proxy gate, not universal OIDC back-channel logout.

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
- `portfolio_swarm_management` connects Caddy and Portainer; `portfolio_swarm_identity` connects Caddy and Authelia; `portfolio_swarm_backend` connects Caddy and Node. Portainer is not attached to the app's trusted backend network.

## Files and redeployment

| Location | Purpose |
| --- | --- |
| `compose.production.yaml` | Portainer service, pinned image, base URL, private network, socket and data mounts |
| `deploy/Caddyfile.swarm` | Protected Portainer route and prefix handling |
| `deploy/authelia/configuration.yml` | OIDC provider, administrator policy, client and callback |
| `scripts/setup-portainer.py` | Idempotent key preparation and API configuration |
| `.auth/secrets/oidc-hmac` | OIDC signing secret |
| `.auth/secrets/oidc-private.pem` | RSA token signing key |
| `.auth/secrets/portainer-client-hash` | PBKDF2 hash of the client secret |
| `.portainer/oauth-client.json` | Matching raw client secret and digest, private to deployment |
| `.portainer/recovery-password` | Initial Portainer `admin` recovery password |
| `.portainer/data/` | Persistent Portainer database, user roles, settings and environment |

The `.portainer/` parent is mode 700 and credential files are mode 600, owned by `opc`. Portainer runs as root and owns its database files, so backups need `sudo`. Both private directories are ignored by Git and excluded from the app image. Do not delete them to reset a failed deployment.

Commit and push changes to `V2`, then merge its PR into `main` to start the automatic deployment. Follow the run in GitHub Actions. To deploy manually, run inside SSH:

```sh
bash /opt/portfolio_redeploy.sh
```

The Swarm deployment preserves existing private account files, updates tasks, then reconciles SSO and the Oracle Swarm agent environment. The helpers use the task network namespace to reach the private API and do not print credentials. Missing or inconsistent credentials stop reconciliation.

For a domain move, set `DOMAIN` in the server's `.env.production` after configuring DNS, then run `bash /opt/portfolio_redeploy.sh --no-pull`. This updates Caddy, Authelia's callback, Portainer's trusted origin, and its OAuth endpoint URLs. The username must still match the existing Authelia account. See [the Docker guide](SWARM.md#changing-the-domain).

## Recovery access

The separate initial Portainer account is `admin`. Its generated password is in `/opt/portfolio/.portainer/recovery-password` and the private local `Portainer recovery login.txt` beside the Oracle SSH key. Use `rithvik` with OAuth for ordinary access. The recovery account remains available to the redeploy helper even when OAuth is enabled.

If shared login is broken, keep public protections in place and diagnose through SSH. Inspect `sudo docker service logs --tail 80 portfolio_auth` and `portfolio_portainer`. After repairing matching configuration/credentials, run `python3 scripts/setup-portainer.py --configure --swarm` and `python3 scripts/swarm-portainer.py` from `/opt/portfolio`. These helpers reach Portainer through Caddy's network namespace. A host SSH tunnel to an overlay task IP is not the recovery method for this setup. Do not disable Authelia or publish an admin port to fix login.

If the `admin` password is intentionally changed through Portainer, update the private recovery-password file to match before redeploying; the CLI file does not reset an existing database password. Update the local recovery record too. Otherwise API reconciliation will stop with an authentication error.

## Backup and restore

Use the private PC helper described in [BACKUPS.md](BACKUPS.md) to snapshot the complete matching credential/database set and certificates. The old `backup-private-state.sh` refuses to run on Swarm. Expect a brief interruption while the helper scales core writers down and restores them.

Keep the archive private and copy it off the VM. Restore each matching credential/database set with its original owners and modes and a compatible source/image version. Preserve Caddy volumes and private OCI/cron configuration separately for full VM recovery, as described in the shared guide.

For an earlier Portainer recovery point, inspect `/home/opc/.config/portfolio-deploy/portainer-stage2-6erYb3rT/` and the image tag `rithvik-portfolio:before-portainer-stage2`. Match the source, private configuration, and auth database archives before restoring. Create fresh backups for ongoing use; these manual recovery points do not update automatically. Use the [app rollback runbook](DOCKER.md#roll-back-an-app-deployment) for routine app recovery.

## Checks and troubleshooting

```sh
cd /opt/portfolio
sudo docker stack services portfolio
sudo docker service logs --tail 80 portfolio_portainer
sudo docker service logs --tail 80 portfolio_auth
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

After changing authentication or routing, sign in through the dashboard, open Portainer, and check the **Oracle Swarm** service/node list. Check that labels and assets load, then sign out and confirm private requests require authentication. Open the public portfolio and contact form to check that both remain available.

References: [Authelia Portainer integration](https://www.authelia.com/integration/openid-connect/clients/portainer/), [Portainer OAuth settings](https://docs.portainer.io/admin/settings/authentication/oauth), [Portainer CLI options](https://docs.portainer.io/advanced/cli).
