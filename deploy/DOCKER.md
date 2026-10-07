# Docker deployment

The local setup runs one Node container. Production runs Node and Caddy in separate containers, with Caddy handling HTTPS. These files prepare deployment; no VM has been deployed by adding them.

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

After pulling updates, rerun the same `up --build -d --wait` command. To inspect or stop the preview:

```sh
docker compose --env-file .env.ip -f compose.ip.yaml logs --tail=100 app
docker compose --env-file .env.ip -f compose.ip.yaml down
```

Once a domain is available, stop this preview and follow the HTTPS setup below before enabling SMTP delivery.

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
5. Set `siteUrl` in `data/portfolio.json` to `https://` followed by that same domain. This controls canonical links and the sitemap; the container build regenerates the pages.
6. Validate and start:

   ```sh
   docker compose --env-file .env.production -f compose.production.yaml config --quiet
   docker compose --env-file .env.production -f compose.production.yaml up --build -d --wait
   docker compose --env-file .env.production -f compose.production.yaml ps
   docker compose --env-file .env.production -f compose.production.yaml logs --tail=100
   ```

7. Open the public HTTPS website and check its pages and CV download. Once SMTP is configured, submit a test message yourself and check the destination inbox and Reply-To behavior. Container health confirms the app responds; it does not confirm DNS, certificate issuance, or email delivery.

Caddy obtains and renews certificates for the configured domain once DNS and network access are correct. Its certificate state persists in `caddy_data`; `caddy_config` also persists. See [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) and the [official Caddy container documentation](https://hub.docker.com/_/caddy).

## Updates and operation

After copying new source or changing `.env.production`, rerun the production `up --build -d --wait` command. This recreates the affected container with the new configuration. A plain `restart` does not reload environment variables. Do not scale the Node service: contact rate limits and duplicate protection are in one process's memory.

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
