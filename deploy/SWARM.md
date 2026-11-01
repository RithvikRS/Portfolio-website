# Run production with Docker Swarm

Use node 1 as the manager and data host. Keep node 2 as a worker. Run the commands below as `opc` on node 1, from `/opt/portfolio`.

## Placement and storage

| Service | Placement | Persistent state |
| --- | --- | --- |
| app | Node 1 | `.notes/` |
| auth | Node 1 | `.auth/` |
| ntfy | Node 1 | `.ntfy/` |
| portainer | Node 1 | `.portainer/` |
| caddy | Node 1 | `portfolio_caddy_data`, `portfolio_caddy_config` |
| node2 | Node 2 | None; authenticated demo at `/node2/` |
| agent | Both nodes | Docker socket and volume access for Portainer |

Keep `portfolio.data=true` on node 1 only and `portfolio.worker=true` on node 2. The five core services each run one replica and use stop-first updates. Never scale these services above one replica: their local databases and certificate storage do not support this deployment pattern.

Caddy publishes 80/TCP and 443/TCP+UDP on node 1. Overlay networks carry service traffic. The dedicated app/Caddy network uses `10.42.0.0/24`; only that network supplies trusted proxy headers. Keep the subnet exclusive to those two services. Agents have no public host port. Open Swarm transport only between the nodes: 7946/TCP+UDP and 4789/UDP, plus 2377/TCP to the manager.

This setup does not provide data failover. If node 1 goes offline, the website and stateful services wait for node 1 to return. A single manager also cannot schedule replacements while offline. Adding shared storage alone does not fix manager quorum, ingress, or application consistency; design those together when adding failover.

## Deploy a change

Push to `V2`, then merge a PR into `main`. GitHub Actions connects to node 1 and runs `portfolio_redeploy.sh`. The `.swarm/enabled` marker selects Swarm deployment.

Keep public service settings in `compose.production.yaml`, placement/image settings in `deploy/swarm.json`, and routing in `deploy/Caddyfile.swarm`. Compose supplies normalized settings to the renderer; **do not run Compose up against production**. Use `deploy/Caddyfile.docker` only for legacy Compose recovery.

The deployment builds and tests the app before replacing tasks, pins other images by digest, creates versioned Docker configs, and checks all services and public/private routes. A failed Swarm update attempts to restore the last successful stack. Fix or revert a bad change through a PR before deploying again.

For a deliberate deployment of the current server checkout:

```sh
cd /opt/portfolio
python3 scripts/swarm-deploy.py deploy
```

This command does not pull Git. Keep server source changes synchronized with the repository. Private settings stay in `.env.production`, `.auth`, `.ntfy`, `.portainer`, and `.notes`. Rendered stack files under `.swarm/` contain credentials; keep the directory private and out of Git and logs. Docker administrators can inspect service environment values.

The app image stays on node 1, where it is built and pinned. A registry is unnecessary for this placement. Add a registry or distribute compatible images before allowing the app onto another node.

## Check production

```sh
sudo docker node ls
sudo docker stack services portfolio
sudo docker stack ps portfolio --no-trunc
python3 scripts/swarm-deploy.py check
python3 scripts/setup-ntfy.py check
```

Expect seven services and eight running tasks: one per service plus the second agent. Open Portainer through `/portainer/` and select **Oracle Swarm** to manage both nodes. Reconnect its environment with `python3 scripts/swarm-portainer.py`; reconcile SSO with `python3 scripts/setup-portainer.py --configure`.

Keep ARM provisioning retired. The migration does not install cron jobs or run Oracle stack triggers. Existing ntfy accounts and iPhone subscriptions continue to work. Health/access checks do not send successful notifications.

## Roll back

After a second successful Swarm release, restore the previous complete service specification:

```sh
cd /opt/portfolio
python3 scripts/swarm-deploy.py rollback
python3 scripts/swarm-deploy.py check
```

The command checks health, swaps the current/previous release pointers, and updates app image tags. It restores service configuration and image selection, **not database contents**. Use a matched private backup for data recovery.

Immediately after the initial migration there is only one Swarm release. The old Compose app remains available as `rithvik-portfolio:previous`, but it predates Swarm proxy trust and is not a supported drop-in Swarm rollback. Use the pre-migration recovery set if the migration itself must be reversed. Stop/remove all Swarm core tasks and confirm they have exited before restoring original Compose source and starting the stopped Compose containers. Never run both against the same data directories. Use the saved original tag inventory and source archive; do not restore old database files unless data recovery is actually needed.

Cleanup runs only after health checks. It retains current/previous app images, preserves volumes and explicit backup tags, and trims the default build cache toward 256 MB. Swarm release tags/specifications remain available for deliberate recovery; they may retain additional images. Review old releases before removing their tags. Read the disk-before/after summary in deployment logs.

## Back up and restore

Use the [Swarm backup guide](BACKUPS.md). The private PC backup pauses the five core services by scaling them to zero, snapshots all state plus Caddy volumes, restores the replica counts, and checks health. Do not use `docker stop` on a Swarm task for a consistent backup: Swarm will replace it.

Keep the original stopped Compose containers until you no longer need migration fallback. Their restart policy is disabled. Do not start them while Swarm runs.
