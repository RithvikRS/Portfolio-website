# Docker and Oracle deployment

Updated **8 October 2026 (Asia/Kolkata)**. The active deployment is at `/opt/portfolio` on Oracle, using `main` and `compose.production.yaml`. Its hostname is `rithvik.ddns.net`, pointing to `144.24.135.201` through No-IP. Caddy serves HTTPS; Node serves the portfolio and admin dashboard; Authelia handles administrator sign-in.

Stages 1 and 2 are deployed: dashboard, shared login, and Portainer. The blog and learning notebook remain stage 3, pending separate approval. See the [admin guide](ADMIN.md) and [Portainer guide](PORTAINER.md) for access, recovery, and backups.

## Which file should I use?

| File | Purpose | Command or entry point |
| --- | --- | --- |
| `Dockerfile` | Builds one Node image, including generated pages, checks, and tests | Compose builds it for the `app` service |
| `compose.yaml` | Local public-site preview, one app container | `docker compose up --build -d --wait` |
| `compose.ip.yaml` | Earlier HTTP preview at a public IP, no SMTP or shared login | Use only for a separate temporary preview |
| `compose.production.yaml` | Current Oracle stack: app, Caddy, Authelia, Portainer, networks and storage | `bash /opt/portfolio_redeploy.sh` on Oracle |
| `.dockerignore` | Allows only named inputs into the image build | Update when adding assets or changing the CV filename |
| `deploy/Caddyfile.docker` | HTTP redirect, HTTPS, `/auth/`, `/admin/`, and `/portainer/` routing | Mounted at `/etc/caddy/site/Caddyfile.docker` |
| `deploy/authelia/configuration.yml` | Non-secret login, session and access rules | Loaded with the template filter and runtime `DOMAIN` |
| `scripts/setup-portainer.py` | Private key preparation and Portainer SSO reconciliation | Called by the redeploy script |
| `deploy/Caddyfile`, `deploy/portfolio.service` | Alternative host Caddy/systemd setup | Not used by the active Docker stack |

A Dockerfile produces an image. Compose describes how to run images together: ports, settings, networks, health checks, and storage. `build` creates an image; `up` creates or updates containers. `up --build` does both. A plain `restart` does not rebuild code or reload changed Compose environment values.

Use one Compose configuration for each deployment; the production and IP files are standalone, not overrides of the local file.

## Current routes and services

| Browser request | Destination | Access |
| --- | --- | --- |
| `http://144.24.135.201/` or HTTP on the hostname | Redirect to `https://rithvik.ddns.net/` | Public |
| `/`, `/Projects.html`, `/Awards.html`, CV and public assets | `app:4173` | Public |
| `/api/contact` | Node contact handler | Same-origin rules for submission |
| `/auth/` | `auth:9091` | Sign-in portal |
| `/admin/` | Authelia session check, then `app:4173` | Administrator only |
| `/portainer/` | Authelia session check, strip prefix, then `portainer:9000` | Administrator via OAuth |
| `/locales/*/translation.json` | Redirect to protected `/portainer/locales/` | Portainer 2.45 translation compatibility |
| `/learn/` | No application installed | No live route |

Only Caddy publishes web ports: TCP 80 and 443, plus UDP 443 for HTTP/3. App port 4173, auth port 9091, and Portainer ports 8000/9000/9443 are not published on the host. SSH is a separate host service.

The `backend` network connects Caddy and the app. Caddy has the configured fixed address `172.30.0.3`. The separate `identity` network connects Caddy and Authelia. The app checks Caddy's exact peer address before accepting administrator identity headers; Caddy strips visitor-supplied identity headers first. Contact rate-limit proxy handling also supports loopback, but this does not grant dashboard access.

The `management` network connects Caddy and Portainer. Portainer has the Docker socket mounted to manage Oracle containers; this grants host-level container control. Its database and settings persist in `.portainer/data/`.

## Local preview

Use Docker Desktop with Linux containers. Compose v2.24 or newer is needed for the optional `.env` file setting. Run from the repository root:

```sh
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

Open **http://localhost:8080**, using that exact hostname for the contact form's origin check. The app listens on 4173 inside the container; Docker maps host port 8080 to it. A container being healthy does not mean host port 4173 is published. Set `CONTAINER_PORT=8081` in `.env` if 8080 is occupied, then run `up` again.

The optional `.env` supplies SMTP settings at runtime. Without them, the contact dialog offers LinkedIn. Local Compose does not start Caddy or Authelia, and the dashboard remains inaccessible. The direct Node preview at `http://127.0.0.1:4173` is a separate workflow in the [project README](../README.md#preview-and-check).

```sh
docker compose logs --tail=100 app
docker compose down
```

After source or asset changes, rerun `docker compose up --build -d --wait`. There is no source bind mount or hot reload in this preview.

## Normal Oracle redeployment

The server already uses `main`; its earlier migration from `V2` is complete. Do not repeat the old branch-creation or IP-preview setup. For each update:

1. Commit development changes locally, including generated public pages when content/templates changed.
2. Merge the development branch (currently `V2`) into `main` and push `main` to GitHub.
3. Connect to Oracle over SSH and run:

   ```sh
   bash /opt/portfolio_redeploy.sh
   ```

`/opt/portfolio_redeploy.sh` is an existing wrapper for `/opt/portfolio/portfolio_redeploy.sh`. Run it inside SSH; do not paste Bash commands into Windows PowerShell. No new script file is needed.

The script locks against concurrent deployments, fetches `main`, permits only a fast-forward update, prepares missing Portainer/OIDC private files, validates Compose/Authelia/Caddy, and builds the app. The image build generates five pages, checks links and the CV, and runs tests with fake mail delivery. It starts auth and Portainer, reconciles Portainer OAuth settings through its private API, verifies Docker access, updates the rest of the stack, and reloads Caddy. Final checks cover the homepage, contact API, auth health, and signed-out dashboard/Portainer access. A Portainer API failure stops deployment before the final Caddy reload.

The current containers serve during the build. Authelia is recreated to load its configuration; its in-memory sessions expire, so sign in again after deployment. The app may briefly restart during replacement. Persistent data and certificates remain.

Stage 1 and 2 files were copied to Oracle before merging into `main`. Include all corresponding code, deployment, and documentation changes in the next merge. The script backs up copied files in a Git stash only when they exactly match `origin/main`; it stops when they differ. Reconcile a reported difference rather than discarding server files or private settings. A Git push alone does not deploy the site.

After changing only the server's saved environment or configuration, rebuild the existing checkout without pulling:

```sh
bash /opt/portfolio_redeploy.sh --no-pull
```

Both commands use private `/opt/portfolio/.env.production`. Editing `.env` on your computer does not update that server file. `scripts/setup-admin.py` is a one-time initializer, not part of every redeployment.

## First setup on a new Linux server

This has already been completed on the current Oracle instance.

1. Install Docker Engine, Compose, Git, Python 3, OpenSSL, curl, and flock. Clone the repository's `main` branch into `/opt/portfolio`. Docker builds Node and pnpm inside the image; they are not needed on the host.
2. Point the hostname at the server. Allow inbound TCP 80/443 in the host firewall and Oracle network rules; UDP 443 is optional. Allow outbound DNS, HTTPS, and SMTP traffic. Keep app/auth ports unpublished.
3. Create runtime settings without overwriting any existing private file:

   ```sh
   cd /opt/portfolio
   cp -n deploy/production.env.example .env.production
   chmod 600 .env.production
   ```

4. Edit `.env.production`. Set `DOMAIN` to the hostname only, without a scheme or path. Add SMTP credentials when ready. `CONTACT_FROM` must be a permitted sender; `CONTACT_TO` is the private destination. Use an SMTP app password where required. Single-quote values containing a literal `$` for Compose. Set `AUTHELIA_UID` and `AUTHELIA_GID` to `id -u` and `id -g` if they are not `1000`.
5. Initialize the administrator as the normal deployment user. The helper uses `sudo -n docker` if required, generates a password/hash and keys, and refuses to overwrite `.auth/`:

   ```sh
   python3 scripts/setup-admin.py
   bash portfolio_redeploy.sh --no-pull
   ```

6. Open the HTTPS site and `/admin/`. Retrieve private bootstrap credentials as described in the [admin guide](ADMIN.md#sign-in). Check actual email delivery manually if needed; health checks and automated tests do not send mail.

On a new server, the repository script works directly. The `/opt/portfolio_redeploy.sh` shortcut is specific to the existing Oracle setup.

## Runtime settings and storage

| Location | Contents | Updated by |
| --- | --- | --- |
| `.env` on your computer | Local preview settings | You; never copied into the image |
| `.env.production` on Oracle | Domain, SMTP, proxy network and account settings | You, privately on Oracle |
| `.auth/secrets/users.yml` | User metadata, groups and Argon2 password hash | One-time setup; manual recovery |
| `.auth/secrets/session-secret` | Session secret | One-time setup; preserve across deployment |
| `.auth/secrets/storage-key` | Database encryption key | One-time setup; retain with the database |
| `.auth/data/` | SQLite database and filesystem notifier output | Auth service |
| `.auth/bootstrap-login.txt` | Initial login details in plaintext | One-time setup; store privately |
| `.auth/secrets/oidc-*`, `portainer-client-hash` | OIDC signing keys and hashed client secret | Portainer helper; preserve |
| `.portainer/recovery-password`, `oauth-client.json` | Recovery password and matching OAuth credentials | Portainer helper; preserve privately |
| `.portainer/data/` | Portainer database, settings, users, and environment | Portainer; back up while stopped |
| `portfolio_caddy_data` volume | Certificates and ACME account state | Caddy |
| `portfolio_caddy_config` volume | Caddy runtime state | Caddy |

`.env*` secrets, `.auth/`, and `.portainer/` stay out of Git and the image build context. Do not share plain `docker compose config` output or full container inspection: they can reveal resolved SMTP settings. Use `config --quiet` for validation. Certificate volumes and private bind directories survive rebuilds and ordinary `compose down`; `down --volumes` removes named volumes.

The app image uses Node 24 and pinned pnpm with the frozen lockfile. Node and Authelia run as non-root users with read-only root filesystems and no extra capabilities. Auth has writable persistent data and temporary `/tmp`. The Compose HTTP health check is active; `server.disable_healthcheck: true` in Authelia only skips writing the image's legacy health-check environment file. Portainer CE 2.45.2 is pinned by digest and runs as root for Docker socket access, without privileged mode. Logs rotate. Limits are 256 MiB each for app and Portainer, 192 MiB each for Caddy and Authelia; Docker and builds need additional memory.

## Caddy changes and new sites

Edit **`deploy/Caddyfile.docker`** for this deployment. Bare `deploy/Caddyfile` belongs to the unused systemd alternative. Caddy mounts the `deploy/` directory so Git file replacement is visible. The redeploy script validates and reloads the correct container path.

For a Caddy-only change already saved on Oracle, validate before reloading:

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.production -f compose.production.yaml exec -T caddy \
  caddy validate --config /etc/caddy/site/Caddyfile.docker --adapter caddyfile &&
sudo docker compose --env-file .env.production -f compose.production.yaml exec -T caddy \
  caddy reload --config /etc/caddy/site/Caddyfile.docker --adapter caddyfile
```

Run reload only after validation succeeds. For changes to Compose, `DOMAIN`, or auth settings, use the redeploy script so containers receive their new environment and configuration.

For a future site, decide whether its application supports a path such as `/tool/` or needs a separate hostname. A path on `rithvik.ddns.net` needs no new DNS record or wildcard. Add the service and a deliberate shared network with Caddy; do not attach unrelated applications to the trusted portfolio backend. Proxy to its service name and internal port, not `localhost` inside the Caddy container. Leave its host port unpublished.

`handle` preserves the request path; `handle_path` strips the matched prefix. For example, `handle_path /tool/*` sends `/tool/page` upstream as `/page`. The application must still generate working asset URLs and redirects for its public base URL. The current `/auth/` route preserves its path because Authelia is configured with that base path. See [Caddy's path handling](https://caddyserver.com/docs/caddyfile/directives/handle_path).

A separate hostname needs its own DNS record and Caddy site block, with DNS pointing to this server. Use the same Caddy service to terminate HTTPS. For a private site, add the appropriate Authelia access rule and the application's supported identity integration before publishing access. Forward authentication alone does not automatically replace an application's own login. See [Authelia's Caddy integration](https://www.authelia.com/integration/proxies/caddy/). Portainer demonstrates both layers: `route` checks the original `/portainer/` URL before stripping its prefix, and OAuth reuses the Authelia identity inside Portainer. Writing services remain pending approval.

For example, after a **public** `tool` service is running on an appropriate shared network and you control the DNS for `tool.example.com`, a new top-level site block would be:

```caddyfile
tool.example.com {
    encode zstd gzip
    reverse_proxy tool:3000
}
```

Replace that example hostname, service, and port with real values. This block provides no login protection. For a path-based public app instead, add its handler inside the existing hostname block before the fallback `handle`, with the app configured for that base path:

```caddyfile
redir /tool /tool/ 308
handle_path /tool/* {
    reverse_proxy tool:3000
}
```

These are documentation examples only; no `tool` service or route is currently deployed.

## Changing the domain

Point the new hostname at Oracle, change `DOMAIN` in `.env.production`, and run `bash /opt/portfolio_redeploy.sh --no-pull`. Compose derives `PUBLIC_ORIGIN`, the build's `SITE_URL`, Authelia's URLs, and Portainer's trusted origin from `DOMAIN`. The helper updates Portainer's authorization, token, user-info, callback, and logout URLs. Caddy requests a certificate for the hostname; Authelia uses it for sign-in and cookies. Keep persistent storage, then sign in again on the new address. Confirm both `/admin/` and `/portainer/` on the new hostname.

DNS directs a browser to the server's IP. The HTTPS request still carries the hostname for TLS and HTTP routing, which Caddy uses to choose a certificate and site. The app's public origin controls contact requests; Authelia uses the hostname for session scope and redirects. This setup redirects HTTP on the IP to the hostname; it is not configured to serve HTTPS directly on the raw IP. This is a configuration description, not a claim that IP certificates are impossible.

Keep the No-IP hostname renewed according to its account requirements. If Oracle's public IP changes, update its DNS record. There is no Cloudflare Pages, Worker, tunnel, or dynamic DNS updater deployed by this setup.

## Status and troubleshooting

Run inside SSH:

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.production -f compose.production.yaml ps
sudo docker compose --env-file .env.production -f compose.production.yaml logs --tail=100 app caddy auth
curl -I https://rithvik.ddns.net/
curl -I https://rithvik.ddns.net/admin/
curl https://rithvik.ddns.net/api/contact
```

The public page should return 200; a signed-out admin request should redirect to `/auth/`. Contact `{"available":true}` indicates configured delivery, not proof of inbox receipt.

| Symptom | Check |
| --- | --- |
| Local container runs but port 4173 is empty | Use `http://localhost:8080` for local Compose; inspect `docker compose ps` |
| SSH identity file cannot be found | Use the full quoted path to the key on the current computer; copying it does not change its identity |
| Public site times out | DNS address, running Caddy, Oracle ingress rules, and host firewall for 80/443 |
| Dashboard is 401 on a local/direct Node preview | Expected: that preview has no authenticated Caddy/Authelia integration |
| Admin route is 502 or sign-in fails | Auth health and logs; see [admin troubleshooting](ADMIN.md#troubleshooting) |
| Redeploy reports server changes differ from `origin/main` | Commit/merge the matching files or reconcile the named server change |
| `Address already in use` on 80/443 | An IP-preview container or host Caddy may still own the port |

## 8 October 2026: memory exhaustion and recovery

The site and SSH became unresponsive while Oracle still reported the VM as Running. A user-initiated reboot restored access. Post-reboot checks confirmed HTTP 200 for the portfolio/auth health, expected signed-out redirects for the dashboard and Portainer, all four containers running, and successful shared login, OAuth, Docker container listing, and logout. Docker is enabled at boot. Load was about 0.1, with approximately 415 MB available RAM and 36% root-disk usage.

The persistent `/var/log/messages` file recorded global out-of-memory events at **7 October 23:31 UTC**, **8 October 06:56 UTC**, and **8 October 09:29 UTC**. All three selected the `dnf` process in `dnf-makecache.service` for termination. At 09:29, DNF held roughly 596 MiB resident memory and the host had only 252 KiB free out of roughly 2.5 GiB swap. That event overlaps the outage and strongly suggests host memory/swap exhaustion; no live resource sample was obtainable during the SSH failure. Earlier events predated Portainer's installation.

The enabled `dnf-makecache.timer` invoked `/usr/bin/dnf makecache --timer`, a background repository-metadata refresh. To prevent that recurring job from exhausting this 1 GB VM again, the following targeted change was applied:

```sh
sudo systemctl disable --now dnf-makecache.timer
sudo systemctl stop dnf-makecache.service
```

The timer is now **disabled/inactive** and the service **inactive**. This does not disable package installation or upgrades, change repositories, or change any update-agent configuration. DNF can refresh metadata during later package operations; those operations can still need significant memory and should be planned for a maintenance window on this small VM. This host setting is separate from Docker Compose and persists across reboots. It is not applied automatically to a new server by `portfolio_redeploy.sh`.

The prior unit definitions and state are saved privately at `/home/opc/.config/portfolio-deploy/dnf-cache-outage-MGfiPW0L/`. To restore scheduled caching after resolving memory capacity, use `sudo systemctl enable --now dnf-makecache.timer`.

The journal was not persistent across the reboot; `/var/log/messages` supplied the evidence. The unrelated failed `mcelog` service reports that it does not support this VM's AMD processor. No package upgrade, reboot, container restart, or logging-service change was performed during this post-reboot check.

References: [DNF makecache command](https://dnf.readthedocs.io/en/latest/command_ref.html#makecache-command) and [DNF metadata timer configuration](https://dnf.readthedocs.io/en/latest/conf_ref.html#metadata-timer-sync).

## Temporary public-IP preview

This is an alternative for a server without a domain, not the current Oracle deployment. Do not start it alongside production: it uses port 80 and the same Compose project name.

```sh
cp deploy/ip.env.example .env.ip
# Set PUBLIC_IP in .env.ip before continuing.
docker compose --env-file .env.ip -f compose.ip.yaml config --quiet
docker compose --env-file .env.ip -f compose.ip.yaml up --build -d --wait
```

It serves the public portfolio over HTTP and does not enable SMTP, Authelia, or the dashboard. Stop it before installing the production stack. Prefer HTTPS production for ongoing use.
