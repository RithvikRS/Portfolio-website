# Docker deployment

The local and public-IP previews each run one Node container. Production runs Node and Caddy in separate containers, with Caddy handling HTTPS. Server deployments use the `main` branch.

## Requirements

- Docker Engine and Docker Compose v2.24 or newer. On Windows, use [Docker Desktop with Linux containers](https://docs.docker.com/desktop/setup/install/windows-install/). On an Ubuntu VM, follow the [official Engine installation guide](https://docs.docker.com/engine/install/ubuntu/), including the Compose plugin.
- Run commands from the repository root.
- The images support Linux AMD64 and ARM64; Docker selects the host architecture. No Node or pnpm installation is needed on the host.

## Local preview

```sh
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

Open **http://localhost:8080**. Use this exact hostname for the contact form's origin check. This is separate from the existing non-container preview on port 4173. Set `CONTAINER_PORT=8081` in `.env` if 8080 is occupied; Compose also updates the allowed origin.

The existing `.env` is optional and is passed into the container at runtime, so its SMTP settings can be reused. Compose overrides the server's host, internal port, origin, and proxy settings for Docker. Nothing edits `.env` or copies it into the image. Without SMTP settings, the site works and the contact dialog offers LinkedIn. Starting a container or running its health check does not send email.

```sh
docker compose logs --tail=100 app
docker compose down
```

This is a built snapshot, with no source bind mount or hot reload. After editing content, CSS, JavaScript, or the CV, rerun `docker compose up --build -d --wait`.

## Oracle VM with a public IP (temporary HTTP preview)

Use `compose.ip.yaml` on its own for an initial deployment without a domain. It publishes port 80 and does not load SMTP credentials, so the contact dialog offers LinkedIn. The existing production HTTPS requirement remains unchanged.

```sh
cp deploy/ip.env.example .env.ip
# Edit PUBLIC_IP in .env.ip to match the instance's public IPv4.
docker compose --env-file .env.ip -f compose.ip.yaml config --quiet
docker compose --env-file .env.ip -f compose.ip.yaml up --build -d --wait
```

Allow inbound TCP 80 in the VM firewall and Oracle network security rules, then open `http://YOUR_PUBLIC_IP/`. Run Docker commands with `sudo` if the login user does not have Docker access. The build sets canonical URLs and the sitemap to this address without changing `data/portfolio.json`.

For updates from Git, follow [Redeploy from main](#redeploy-from-main). To inspect or stop the preview:

```sh
docker compose --env-file .env.ip -f compose.ip.yaml logs --tail=100 app
docker compose --env-file .env.ip -f compose.ip.yaml down
```

Once a domain is available, stop this preview and follow the HTTPS setup below before enabling SMTP delivery.

## Switch the existing Oracle checkout from V2 to main (once)

First commit the deployment changes, merge `V2` into `main`, and push `main` to GitHub. Include `Dockerfile`, `scripts/build.mjs`, `compose.ip.yaml`, `deploy/ip.env.example`, and this guide. Keep `.env.ip` and credentials out of Git.

The existing Oracle checkout at `/opt/portfolio` was cloned with `--single-branch` for `V2`. It also has the initial deployment changes copied in as tracked modifications and untracked files. Run this block in the Oracle SSH session after the merge is pushed:

```sh
(
  set -eu
  cd /opt/portfolio
  git remote set-branches origin main
  git fetch origin
  git cat-file -e origin/main:compose.ip.yaml
  git stash push --include-untracked -m "Oracle deployment backup before switching to main"
  git switch --create main --track origin/main
  sudo docker compose --env-file .env.ip -f compose.ip.yaml config --quiet
  sudo docker compose --env-file .env.ip -f compose.ip.yaml up --build -d --wait
  sudo docker compose --env-file .env.ip -f compose.ip.yaml ps
)
```

The remote setting makes future fetches track `main`. The file check confirms that the IP deployment configuration reached GitHub before changing the checkout. The stash preserves the server's uncommitted files; ignored `.env.ip` stays in place. Keep this stash as a backup: the merged branch already supplies those deployment changes, so it does not need to be reapplied. The parenthesized block stops on an error without closing the SSH session.

This block creates the local `main` branch once. If it already exists, use the redeployment block below instead. Switching Git branches does not change the running container; Compose replaces it after the build succeeds.

## Redeploy from main

After the one-time switch, commit and push each update to `main`, then run this block in the Oracle SSH session:

```sh
(
  set -eu
  cd /opt/portfolio
  git switch main
  git pull --ff-only origin main
  sudo docker compose --env-file .env.ip -f compose.ip.yaml config --quiet
  sudo docker compose --env-file .env.ip -f compose.ip.yaml up --build -d --wait
  sudo docker compose --env-file .env.ip -f compose.ip.yaml ps
)
```

The build runs the site checks and tests before replacing the container. `--ff-only` stops if the server branch has diverged instead of creating a deployment merge. If Git reports conflicting local changes, reconcile or back them up before continuing. The server builds a snapshot, so pulling code alone does not update the website.

Verify `http://144.24.135.201/` after the command succeeds. For startup problems, run:

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.ip -f compose.ip.yaml logs --tail=100 app
```

## Oracle VM with a domain and HTTPS

Use `compose.production.yaml` on its own, not as an override of the local file. This keeps the Node port off the host's published ports.

1. Install Docker Engine and the Compose plugin, and copy or clone the repository onto the VM. Do not run the systemd/Caddy host setup at the same time: it uses the same public ports.
2. Point your domain's DNS at the VM. Use one canonical hostname. Allow inbound TCP 80 and 443 in the VM firewall and Oracle security rules; UDP 443 is optional for HTTP/3. Allow outbound DNS, HTTPS, and your SMTP provider's port. Port 4173 stays unpublished.
3. Create the production settings file:

   ```sh
   cp deploy/production.env.example .env.production
   chmod 600 .env.production
   ```

4. Edit `.env.production`: set `DOMAIN` to your real hostname, without a scheme or path. Add SMTP settings when ready. For your Gmail sender, these are `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_SECURE=false`, `SMTP_USER=rithvik.notifications@gmail.com`, `CONTACT_FROM=rithvik.notifications@gmail.com`, and `CONTACT_TO=rithvik.career@gmail.com`. `SMTP_PASS` must be an app password, not the normal Gmail password. Leave credentials blank to keep messaging disabled. Single-quote any environment value containing a literal `$` so Compose does not interpolate it.
5. The production build derives `SITE_URL` from `DOMAIN`. This sets canonical links and the sitemap to the HTTPS hostname without changing the default URL in `data/portfolio.json`.
6. Validate and start:

   ```sh
   docker compose --env-file .env.production -f compose.production.yaml config --quiet
   docker compose --env-file .env.production -f compose.production.yaml up --build -d --wait
   docker compose --env-file .env.production -f compose.production.yaml ps
   docker compose --env-file .env.production -f compose.production.yaml logs --tail=100
   ```

7. Open the public HTTPS website and check its pages and CV download. Once SMTP is configured, submit a test message yourself and check the destination inbox and Reply-To behavior. Container health confirms the app responds; it does not confirm DNS, certificate issuance, or email delivery.

Caddy obtains and renews certificates for the configured domain once DNS and network access are correct. Its certificate state persists in `caddy_data`; `caddy_config` also persists. See [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) and the [official Caddy container documentation](https://hub.docker.com/_/caddy).

### No-IP hostname

The configured hostname is `rithvik.ddns.net`, with a No-IP A record pointing to `144.24.135.201`. Wildcard DNS is not required for this hostname. Keep `DOMAIN=rithvik.ddns.net` in the server's ignored `.env.production` file. Caddy redirects HTTP requests, including visits to the IP address, to this HTTPS hostname.

Confirm the free hostname every 30 days in No-IP to keep it active. If the Oracle public IP changes, update the A record. An automatic DNS update client, if used, should run on Oracle so it reports the server's address.

Use the production commands below for this HTTPS deployment. The `compose.ip.yaml` commands are only for the earlier HTTP preview. To move to a purchased domain later, point its DNS at Oracle, change `DOMAIN` in `.env.production`, and rebuild with the production command; Caddy will request a certificate for the new hostname. Keep the certificate volumes during this change.

## Updates and operation

The Oracle shortcut is `/opt/portfolio_redeploy.sh`. It runs the versioned `portfolio_redeploy.sh` in `/opt/portfolio`. After committing your development changes, merging them into `main`, and pushing `main`, run this single command in SSH:

```sh
bash /opt/portfolio_redeploy.sh
```

The script fetches `main`, allows only a fast-forward update, validates Compose and Caddy, builds the app and generated pages, runs the image's link checks and tests, starts the stack, reloads Caddy, and checks the public HTTPS site and contact API. It keeps the current containers serving during the build and preserves the certificate volumes. Docker can reuse cached build steps when their inputs are unchanged.

The server reads its saved `.env.production`, including the deployed SMTP credentials, on every run. This file remains private, with mode `600`, and is neither replaced from Git nor baked into the image. Updating your computer's `.env` does not update the server automatically; copy any changed mail settings securely to the server's `.env.production` separately.

Include `portfolio_redeploy.sh` and the deployment configuration changes in your next commit and merge to `main` before the first normal run. The script can reconcile the initial copied deployment files when they exactly match the versions pushed to `main`: it saves those server copies in a Git stash before updating. It stops if any server changes differ, instead of overwriting them. A concurrent deployment or divergent server commit also stops the script.

To rebuild the existing server checkout after changing only its environment settings, skip the Git update:

```sh
bash /opt/portfolio_redeploy.sh --no-pull
```

On another server, the repository copy can be run directly with `bash /opt/portfolio/portfolio_redeploy.sh`. A plain Docker `restart` does not reload environment variables; the script uses Compose `up` to recreate affected containers. Do not scale the Node service: contact rate limits and duplicate protection are in one process's memory.

To refresh the base images and rebuild explicitly:

```sh
docker compose --env-file .env.production -f compose.production.yaml pull caddy
docker compose --env-file .env.production -f compose.production.yaml build --pull app
docker compose --env-file .env.production -f compose.production.yaml up -d --wait
```

To stop production while preserving certificates:

```sh
docker compose --env-file .env.production -f compose.production.yaml down
```

Keep the named volumes; adding `--volumes` deletes the stored certificates. Back up `.env.production` privately and preserve Caddy's data volume when moving the deployment. Avoid sharing the output of plain `docker compose config` or container inspection: those can reveal environment secrets. Use `config --quiet` for validation.

## Container details

- The multi-stage image uses Node 24 on Debian slim. pnpm is pinned and installs production dependencies from the frozen lockfile. The build regenerates pages, checks links, and runs tests with fake mail delivery. The final stage excludes build tools, test files, and pnpm's installation.
- `.dockerignore` permits only named build inputs. Credentials, Git history, local dependencies, and the old CV are excluded. When adding assets or changing the CV filename, update that allowlist.
- Node runs as a non-root user with a read-only filesystem, no extra Linux capabilities, a health check, and a graceful shutdown timeout. Logs rotate. The configured runtime limits are 256 MiB for Node and 192 MiB for Caddy; builds and Docker itself need additional memory.
- Production uses a dedicated bridge network. Caddy gets `172.30.0.3` and overwrites `X-Real-IP`; Node trusts that exact proxy address plus loopback. Other peers cannot bypass rate limits by supplying that header. If the default subnet overlaps a VPN or existing Docker network, change both `DOCKER_SUBNET` and `CADDY_IP` to a matching unused subnet/address before starting. Do not place unrelated containers on this network.
- Both containers need outbound network access, including Node's SMTP connection. The backend network therefore is not marked `internal`. Only Caddy publishes public ports.
- The current configuration assumes Caddy directly receives visitor traffic. If adding a CDN or another reverse proxy, update client-IP trust before enabling it.

The existing [contact behavior and limits](README.md#contact-behavior-and-limits) still apply. The [host-based deployment guide](README.md) remains available if you choose to run without Docker.
