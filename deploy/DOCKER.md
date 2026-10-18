# Docker and Oracle deployment

Use `/opt/portfolio` on Oracle with the `main` branch and `compose.production.yaml`. Point `rithvik.ddns.net` to `144.24.135.201`. Caddy handles HTTPS, Node serves the portfolio and admin dashboard, and Authelia handles administrator sign-in.

Use the dashboard for shared access to Portainer and Fieldnotes. Follow the [writing guide](FIELDNOTES.md) to edit posts and back up content, the [admin guide](ADMIN.md) to manage account access, and the [Portainer guide](PORTAINER.md) to manage containers.

## Which file should I use?

| File | Purpose | Command or entry point |
| --- | --- | --- |
| `Dockerfile` | Builds one Node image, including generated pages, checks, and tests | Compose builds it for the `app` service |
| `compose.yaml` | Local public-site preview, one app container | `docker compose up --build -d --wait` |
| `compose.ip.yaml` | Earlier HTTP preview at a public IP, no SMTP or shared login | Use only for a separate temporary preview |
| `compose.production.yaml` | Current Oracle stack: app, Caddy, Authelia, Portainer, ntfy, networks and storage | `bash /opt/portfolio_redeploy.sh` on Oracle |
| `compose.rollback.yaml` | App-only overlay using the retained previous image | See [image cleanup and rollback](#image-cleanup-and-rollback) |
| `.dockerignore` | Allows only named inputs into the image build | Update when adding assets or changing the CV filename |
| `deploy/Caddyfile.docker` | HTTP redirect, HTTPS, `/auth/`, `/admin/`, and `/portainer/` routing | Mounted at `/etc/caddy/site/Caddyfile.docker` |
| `deploy/authelia/configuration.yml` | Non-secret login, session and access rules | Loaded with the template filter and runtime `DOMAIN` |
| `scripts/setup-notes.py` | Creates/verifies private `.notes/` for the Node user | Called on every redeploy; preserves entries |
| `scripts/setup-portainer.py` | Private key preparation and Portainer SSO reconciliation | Called by the redeploy script |
| `scripts/setup-ntfy.py` | Private notification accounts, topic permissions, and HTTPS checks | Called by the redeploy script |
| `scripts/deploy-images.py` | Retains successful app images and cleans unused images/cache | Called before the build and after all deployment checks |
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
| `/blog/`, `/learn/` and their article paths | `app:4173` | Published writing only |
| `/admin/notes/` and `/admin/notes/api/*` | Existing `/admin/*` gate, then app | Administrator only |
| Separate `NTFY_DOMAIN` hostname | `ntfy:8080` | ntfy credentials and topic permissions |

Only Caddy publishes public web ports: TCP 80 and 443, plus UDP 443 for HTTP/3. ntfy binds port 2586 to loopback for the local ARM script. App port 4173, auth port 9091, and Portainer ports 8000/9000/9443 are not published on the host. SSH is a separate host service.

The `backend` network connects Caddy and the app. Caddy has the configured fixed address `172.30.0.3`. The separate `identity` network connects Caddy and Authelia. The app checks Caddy's exact peer address before accepting administrator identity headers; Caddy strips visitor-supplied identity headers first. Contact rate-limit proxy handling also supports loopback, but this does not grant dashboard access.

The `management` network connects Caddy and Portainer. Portainer has the Docker socket mounted to manage Oracle containers; this grants host-level container control. Its database and settings persist in `.portainer/data/`.

The `notifications` network connects Caddy and ntfy. ntfy stores its cache and authentication database in `.ntfy/data/`; account credentials and notification state stay in the private `.ntfy/` directory.

## Local preview

Use Docker Desktop with Linux containers. Compose v2.24 or newer is needed for the optional `.env` file setting. Run from the repository root:

```sh
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

Open **http://localhost:8080**, using that exact hostname for the contact form's origin check. The app listens on 4173 inside the container; Docker maps host port 8080 to it. A container being healthy does not mean host port 4173 is published. Set `CONTAINER_PORT=8081` in `.env` if 8080 is occupied, then run `up` again.

The optional `.env` supplies SMTP settings at runtime. Without them, the contact dialog offers LinkedIn. Local Compose does not start Caddy or Authelia, and the dashboard remains inaccessible. The direct Node preview at `http://127.0.0.1:4173` is a separate workflow in the [project README](../README.md#run-locally).

```sh
docker compose logs --tail=100 app
docker compose down
```

After source or asset changes, rerun `docker compose up --build -d --wait`. There is no source bind mount or hot reload in this preview.

## Normal Oracle redeployment

Keep the server checkout on `main` and make development changes on `V2`. For each update:

1. Commit development changes locally, including generated public pages when content/templates changed.
2. Push the development branch (currently `V2`) and merge its pull request into `main`.
3. The **Deploy portfolio** GitHub Actions workflow connects over SSH and runs the deployment script automatically. Check the run in the Actions tab. To deploy manually instead, connect to Oracle over SSH and run:

   ```sh
   bash /opt/portfolio_redeploy.sh
   ```

`/opt/portfolio_redeploy.sh` is an existing wrapper for `/opt/portfolio/portfolio_redeploy.sh`. Run it inside SSH; do not paste Bash commands into Windows PowerShell. No new script file is needed.

The script locks against concurrent deployments, fetches `main`, permits only a fast-forward update, prepares `.notes/` and missing Portainer/OIDC private files, validates Compose/Authelia/Caddy, and builds the app. The image build generates five pages, checks links and the CV, and runs tests with fake mail delivery. It starts auth and Portainer, reconciles Portainer OAuth settings through its private API, verifies Docker access, updates the rest of the stack, and reloads Caddy. Final checks cover the homepage, contact API, auth health, and signed-out dashboard/Portainer/writing-export access and both public writing collections. ntfy preparation preserves account credentials, starts the service, and reconciles topic permissions. HTTPS and topic access checks must pass before cleanup. A Portainer API failure stops deployment before the final Caddy reload.

The current containers serve during the build. Authelia is recreated to load its configuration; its in-memory sessions expire, so sign in again after deployment. The app may briefly restart during replacement. Persistent data and certificates remain.

Keep server edits in sync with `origin/main`. The script saves uncommitted server edits in a Git stash only when they exactly match `origin/main`; it stops when they differ. Reconcile any reported differences before deploying. Pushing `V2` alone does not deploy; merging its PR into `main` does. The workflow uses `pull_request_target` with a merged-only condition, no PR checkout, and the `production` environment restricted to `main`.

After changing only the server's saved environment or configuration, rebuild the existing checkout without pulling:

```sh
bash /opt/portfolio_redeploy.sh --no-pull
```

Both commands use private `/opt/portfolio/.env.production`. Editing `.env` on your computer does not update that server file. `scripts/setup-admin.py` is a one-time initializer, not part of every redeployment.

## Image cleanup and rollback

The deployment runs the image-retention tests, then preserves the healthy running app before building. It updates the recovery tags and performs cleanup **only after every container and HTTP check succeeds**:

| Image tag | Purpose |
| --- | --- |
| `rithvik-portfolio:production` | Most recently built candidate; it can be a failed deployment |
| `rithvik-portfolio:current` | Last app image that passed the complete deployment checks |
| `rithvik-portfolio:previous` | Successful app image before `current`, retained for rollback |

On the first run, `current` is initialized from the actual healthy app container, not the mutable `production` tag. A failed build/start/check does not rotate the recovery tags or run cleanup. A retry retains the last successful image even if a failed candidate is still running. Redeploying the same image keeps the existing distinct rollback. A brand-new installation has no previous image until a second distinct image succeeds.

Cleanup removes untagged, unused portfolio app images bearing `io.github.rithvikrs.portfolio.app=true`. When the previous tag rotates, its retired image is also eligible for non-forced removal if it has no other tags or digest references; Docker protects images used by containers. Explicit manual backup tags, other applications' images, containers, volumes, networks, certificates, `.env.production`, `.auth/`, `.portainer/`, `.notes/`, and `.ntfy/` are preserved. No `docker system prune`, volume prune, or `docker image prune --all` is used.

Unused cache in the Docker daemon's **shared default builder** is pruned with `docker buildx prune --builder default --all --force --max-used-space 256MB`. This cache is shared with other builds on the host, so future builds of any project may take longer; it is not application data. Docker removes the least recently used reclaimable records to target 256 MB; records/layers still in use may prevent reaching that target. Other Buildx builders are not cleaned. Cleanup errors are logged as warnings after a healthy deployment; failure to establish the recovery tags stops before cleanup.

Read **Cleanup disk usage before** and **Cleanup disk usage after** in the deployment log for total, used, and available space on the filesystem containing Docker's data directory (`DockerRootDir`). The script uses GNU `df` with byte precision immediately before any retired-image removal and after both prune commands finish. The **Net disk space freed during cleanup** line subtracts final used space from initial used space, so it covers all three cleanup steps. Each step also has its own label; a prune command's `0 B` total applies only to that command.

Treat the summary as the observed filesystem change, not a sum of Docker image sizes. Shared layers count once, while unrelated server writes and delayed Docker reclamation can affect the result. A net increase prints **Net disk usage increased during cleanup**. If either measurement fails or filesystem capacity changes, the script reports the summary as unavailable and keeps the existing cleanup and rollback behavior. If you move Docker or containerd data onto separate filesystems, inspect those filesystems separately; this summary covers only the filesystem containing `DockerRootDir`.

Use the normal deployment command to run retention and cleanup automatically after successful checks. When first introducing these steps on another existing server, run deployment twice: the initial run finishes the script version loaded before Git updates it.

## Roll back an app deployment

Rollback is manual. Use your normal interactive SSH login to the AMD server; the dedicated Actions key is restricted to running the deployment script. Run the commands below in the **server's Bash shell**, not Windows PowerShell. Let an active deployment finish and avoid new PR merges or reruns until recovery is complete. The rollback command also takes the deployment lock so it refuses to overlap a running deployment.

### 1. Choose the recovery image

| Situation | Recovery choice |
| --- | --- |
| Configuration validation or the image build failed, and the existing site still works | Usually no app rollback is needed. Fix the reported error before deploying again. |
| A deployment failed during app startup or endpoint checks | Use `current`: it still points to the last successful app image. |
| Deployment passed all checks, but a functional problem was discovered afterward | Use `previous`: the successful deployment already moved the new image to `current`. |
| Only image/cache cleanup reported a warning | The app passed deployment checks; investigate cleanup separately. |

For example, if B was successful and deployment C fails, `current` remains B and `previous` remains A. Restoring `previous` would skip B. If C passes deployment checks, the tags become `current=C` and `previous=B`.

Inspect the available images and container state before choosing:

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.production -f compose.production.yaml ps --all
for tag in current previous; do
  printf '\n%s\n' "$tag"
  sudo docker image inspect "rithvik-portfolio:$tag" \
    --format '{{.Id}} revision={{index .Config.Labels "org.opencontainers.image.revision"}}'
done
sudo docker container inspect portfolio-app-1 \
  --format '{{.Image}} running={{.State.Running}} health={{if .State.Health}}{{.State.Health.Status}}{{end}}'
```

Use the image IDs and revision labels to identify the intended version. Older retained images may report `revision=unknown`. If the chosen tag is missing, stop and inspect the available manual backup tags; do not substitute `production`, which may contain the failed build. A failure in the image-retention step itself also needs inspection of the actual tags before selecting a recovery image.

### 2. Restore the app and check it

The block below defaults to **`rollback_tag=current` for a failed deployment**. Change that one line to **`rollback_tag=previous`** when undoing a deployment that passed its checks. Update `site_origin` if the domain has changed. Paste the entire block into the server's Bash shell:

```sh
cd /opt/portfolio
(
  set -euo pipefail
  flock -n 9 || { printf 'Another deployment is running.\n' >&2; exit 1; }

  rollback_tag=current
  site_origin=https://rithvik.ddns.net
  case "$rollback_tag" in
    current|previous) ;;
    *) printf 'Choose current or previous.\n' >&2; exit 1 ;;
  esac
  rollback_image="$(sudo -n docker image inspect "rithvik-portfolio:$rollback_tag" --format '{{.Id}}')"
  sudo -n docker image inspect "$rollback_image" \
    --format '{{.Id}} revision={{index .Config.Labels "org.opencontainers.image.revision"}}'

  sudo -n docker compose --env-file .env.production \
    -f compose.production.yaml -f - \
    up --no-build --pull never --no-deps -d --wait --wait-timeout 180 app <<EOF
services:
  app:
    image: "$rollback_image"
EOF

  app_state="$(sudo -n docker container inspect portfolio-app-1 \
    --format '{{.Image}} {{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}')"
  [[ "$app_state" == "$rollback_image true healthy" ]] || {
    printf 'The selected app image is not running and healthy.\n' >&2; exit 1;
  }
  for path in / /api/contact /blog/ /learn/ /auth/api/health; do
    status="$(curl --silent --show-error --connect-timeout 10 --max-time 30 \
      --output /dev/null --write-out '%{http_code}' "$site_origin$path")"
    [[ "$status" == 200 ]] || {
      printf 'Public check failed: %s returned %s\n' "$path" "$status" >&2; exit 1;
    }
  done
  for path in /admin/ /portainer/ /admin/notes/api/export; do
    status="$(curl --silent --show-error --connect-timeout 10 --max-time 30 \
      --output /dev/null --write-out '%{http_code}' "$site_origin$path")"
    case "$status" in
      302|303|401) ;;
      *) printf 'Private access check failed: %s returned %s\n' "$path" "$status" >&2; exit 1 ;;
    esac
  done

  sudo -n docker image tag "$rollback_image" rithvik-portfolio:current
  printf 'Restored %s and recorded it as current.\n' "$rollback_image"
) 9>.git/portfolio-deploy.lock
```

This resolves the chosen tag to an image ID and replaces only the app container. It does not build or download an image, restart dependencies, or run cleanup. The temporary Compose override comes from standard input and leaves repository files unchanged. The existing `compose.rollback.yaml` always selects `previous`; the block above supports either recovery target. See the [Compose file override reference](https://docs.docker.com/reference/cli/docker/compose/) and [startup options](https://docs.docker.com/reference/cli/docker/compose/up/).

The command records the restored image as `current` only after container health, public endpoints, and signed-out access checks pass. After restoring `previous`, both `current` and `previous` can temporarily refer to that same image. If a check fails, the app may already have been replaced; the command stops without promoting the image and does not automatically undo the attempted rollback.

### 3. Verify the problem is fixed

Open the portfolio, `/blog/`, and `/learn/`, then sign in and check `/admin/`, `/admin/notes/`, and `/portainer/`. Exercise the specific feature that prompted the rollback; automated health checks cannot catch every functional problem. The contact health check confirms configuration without sending email.

If the app does not recover, inspect recent logs privately:

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.production -f compose.production.yaml logs --tail=100 app caddy auth
```

Image rollback keeps the current Compose settings, `.env.production`, `.auth/`, `.portainer/`, `.notes/`, and certificate volumes. It does **not** restore source files, infrastructure configuration, or data snapshots. An older app must support the current settings and writing format. If a deployment broke Caddy/Authelia/Portainer configuration or changed data incompatibly, app rollback alone will not repair it; use the relevant configuration fix or [data recovery guide](ADMIN.md#backups-and-recovery-data).

### 4. Resume normal deployments

Fix or revert the faulty change in a development branch, then merge its PR into `main`. The next normal deployment rebuilds from `main`, using the restored `current` image as the recovery baseline. Do not rerun the failed deployment or run the normal redeploy shortcut before the fix is ready: both can replace the restored app with the same faulty version. `--no-pull` is also a rebuild of the server checkout, not an image rollback.

The rollback itself does not change Git history or the `production` tag. A successful new deployment updates the normal tags and resumes cleanup. The retained image remains available locally until a later successful deployment rotates it out of retention; it is not a substitute for backups of persistent data.

## First setup on a new Linux server

Follow these steps when provisioning a new server. For an existing installation, use [normal redeployment](#normal-oracle-redeployment).

1. Install Docker Engine, Compose, Git, Python 3, OpenSSL, curl, and flock. Clone the repository's `main` branch into `/opt/portfolio`. Docker builds Node and pnpm inside the image; they are not needed on the host.
2. Point the hostname at the server. Allow inbound TCP 80/443 in the host firewall and Oracle network rules; UDP 443 is optional. Allow outbound DNS, HTTPS, and SMTP traffic. Keep app/auth ports unpublished.
3. Create runtime settings without overwriting any existing private file:

   ```sh
   cd /opt/portfolio
   cp -n deploy/production.env.example .env.production
   chmod 600 .env.production
   ```

4. Edit `.env.production`. Set `DOMAIN` to the portfolio hostname and `NTFY_DOMAIN` to a separate ntfy hostname, both without a scheme or path. Point both at this server. Add SMTP credentials when ready. `CONTACT_FROM` must be a permitted sender; `CONTACT_TO` is the private destination. Use an SMTP app password where required. Single-quote values containing a literal `$` for Compose. The current Node writing mount and helper require deployment UID/GID `1000:1000`; align the container user and mount ownership deliberately on a different host. Authelia and ntfy UID/GID settings must also match their own directories.
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
| `.notes/` | Private drafts, published snapshots, and trash; mounted at `/writing` | Node app; back up while stopped |
| `.ntfy/` | Notification accounts, SQLite databases, iPhone login sheet, and ARM alert state | ntfy and its setup/notifier scripts; preserve privately |
| `portfolio_caddy_data` volume | Certificates and ACME account state | Caddy |
| `portfolio_caddy_config` volume | Caddy runtime state | Caddy |

`.env*` secrets, `.auth/`, `.portainer/`, `.notes/`, and `.ntfy/` stay out of Git and the image build context. Do not share plain `docker compose config` output or full container inspection: they can reveal resolved SMTP settings. Use `config --quiet` for validation. Certificate volumes and private bind directories survive rebuilds and ordinary `compose down`; `down --volumes` removes named volumes.

The app image uses Node 24 and pinned pnpm with the frozen lockfile. Node and Authelia run as non-root users with read-only root filesystems and no extra capabilities. Node has writable `/writing` for Fieldnotes; Auth has writable persistent data and temporary `/tmp`. The Compose HTTP health check is active; `server.disable_healthcheck: true` in Authelia only skips writing the image's legacy health-check environment file. Portainer CE 2.45.2 is pinned by digest and runs as root for Docker socket access, without privileged mode. Logs rotate. Limits are 256 MiB each for app and Portainer, 192 MiB each for Caddy and Authelia, and 128 MiB for ntfy; Docker and builds need additional memory.

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

A separate hostname needs its own DNS record and Caddy site block, with DNS pointing to this server. Use the same Caddy service to terminate HTTPS. For a private site, add the appropriate Authelia access rule and the application's supported identity integration before publishing access. Forward authentication alone does not automatically replace an application's own login. See [Authelia's Caddy integration](https://www.authelia.com/integration/proxies/caddy/). Portainer demonstrates both layers: `route` checks the original `/portainer/` URL before stripping its prefix, and OAuth reuses the Authelia identity inside Portainer. Fieldnotes uses the existing authenticated `/admin/*` handler; its public `/blog/*` and `/learn/*` pages use the existing fallback. No extra Caddy rule is needed for its articles.

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

## Private notifications

Set `NTFY_DOMAIN=ntfy.144.24.135.201.sslip.io` in the AMD server's `.env.production`. Use the [ntfy guide](NTFY.md) for initial setup, private topic permissions, ARM notifications, and iPhone instructions. Keep `.ntfy/` private and preserve it during redeployments. ntfy uses its own authentication for native clients and a separate Caddy hostname; it does not use Authelia redirects.

## Changing the domain

Point the new hostname at Oracle, change `DOMAIN` in `.env.production`, and run `bash /opt/portfolio_redeploy.sh --no-pull`. Compose derives `PUBLIC_ORIGIN`, the build's `SITE_URL`, Authelia's URLs, and Portainer's trusted origin from `DOMAIN`. The helper updates Portainer's authorization, token, user-info, callback, and logout URLs. Caddy requests a certificate for the hostname; Authelia uses it for sign-in and cookies. Keep persistent storage, then sign in again on the new address. Confirm `/admin/`, `/portainer/`, `/admin/notes/`, `/blog/`, and `/learn/` on the new hostname.

DNS directs a browser to the server's IP. The HTTPS request still carries the hostname for TLS and HTTP routing, which Caddy uses to choose a certificate and site. The app's public origin controls contact and writing mutations and canonical article URLs; Authelia uses the hostname for session scope and redirects. This setup redirects HTTP on the IP to the hostname; it is not configured to serve HTTPS directly on the raw IP. This is a configuration description, not a claim that IP certificates are impossible.

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

## Manage memory on the AMD server

If the site and SSH become unresponsive, check `/var/log/messages` for out-of-memory events after recovering access. Inspect available memory with `free -h` and follow the [status checks](#status-and-troubleshooting) to check containers and endpoints.

Keep `dnf-makecache.timer` disabled on this 1 GB VM to avoid scheduled package-metadata refreshes competing with the application for memory. Apply this host setting with:

```sh
sudo systemctl disable --now dnf-makecache.timer
sudo systemctl stop dnf-makecache.service
```

Check the timer with `systemctl is-enabled dnf-makecache.timer` and `systemctl is-active dnf-makecache.timer`; expect `disabled` and `inactive`. Continue installing packages and updates as needed, but plan memory-intensive package operations for a maintenance window. Disabling the timer leaves package installation and upgrades available.

Apply this setting separately from Docker Compose; `portfolio_redeploy.sh` does not configure it on a new server. To restore scheduled caching after increasing available memory, run `sudo systemctl enable --now dnf-makecache.timer`. Find the saved timer configuration under `/home/opc/.config/portfolio-deploy/dnf-cache-outage-MGfiPW0L/` if you need the earlier host settings.

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
