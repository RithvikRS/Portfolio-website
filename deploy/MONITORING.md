# Monitoring

Open **https://uptime.144.24.135.201.sslip.io/**. Sign in through Authelia with an account in `admins`, then use the separate Kuma administrator login. Find that credential on the PC in `C:\Users\Rithvik\Documents\Portfolio-private-backups\monitoring-setup\admin.json`; keep it out of Git, logs, and screenshots.

## Placement and access

Run Uptime Kuma 2.5.9 by immutable image digest on AMD node 2. Keep its SQLite database and uploads in `/srv/swarm/uptime_kuma`, owned by `1000:1000`. Use one replica and stop-first updates/rollback. The service has a 320 MiB memory limit, 128 MiB reservation, 0.5 CPU limit, 192 MiB Node heap limit, a read-only root filesystem, and bounded logs. Use a long-syntax `type: tmpfs` mount for `/tmp`; Swarm ignores the Compose short-form `tmpfs` field. SQLite migrations need this writable scratch space. Monitor actual usage; swap does not increase physical RAM.

The manager passes the pinned worker image digest to Swarm without pulling or unpacking it locally. Workers verify and download the image themselves; keep image backup coverage on the worker.

Only Caddy and Kuma join the private, non-attachable monitoring overlay. Do not publish Kuma's port 3001 or Caddy's internal health port 8081. Never mount the Docker socket in Kuma. Caddy exposes only explicit backend health paths on 8081; it does not offer an alternate application frontend there.

Protect all Kuma paths with Authelia, including `/socket.io`, API routes, assets, and status pages. Keep native Kuma authentication enabled and do not create public status pages. Authelia authorizes the administrator group; Kuma does not become a multi-user application simply because it sits behind SSO.

The three browser hostnames use separate, narrowly scoped session cookies. Expect to sign in on each hostname. Never widen a cookie to `sslip.io`. Login pages and required authentication endpoints must remain reachable before login.

Keep the public portfolio, published blog/learning pages, and their required public APIs accessible. Gate administration, Portainer, node 2, Kuma, and the ntfy browser interface. Preserve ntfy's native authenticated API exception for iPhone subscriptions and publishing. ntfy still applies per-account topic permissions; a browser Authelia session does not replace those permissions.

## Checks and alert policy

- Check public portfolio HTTPS and its TLS certificate.
- Check portfolio, Authelia, Portainer, ntfy, and node 2 through the unpublished health listener.
- Check that Kuma, portfolio administration, and the ntfy browser interface reject unauthenticated requests. Do not follow redirects: a login page returning 200 must not count as a working backend.
- Check every 60 seconds. Retry failures twice at 30-second intervals before declaring an outage. Send an outage alert and a recovery alert; set `resendInterval` to zero to disable repeated outage reminders.
- Keep 30 days of heartbeat history. Disable response-body storage and domain-expiry lookup; retain TLS-expiry warnings for the public portfolio.

Kuma publishes to the existing `arm-provisioning` ntfy topic as `kuma-publisher`, with write-only access. The iPhone keeps its existing read-only account and subscription. Save the publisher credential in the manager's private `.ntfy/monitoring-publisher.json` and the configured Kuma database, never in the catalog or environment variables.

A cluster-wide outage can disable both Kuma and ntfy. External monitoring with an independent alert path remains a separate follow-up. These checks also do not prove cross-user authorization or business-data freshness.

## Configure or change monitors

Use the dashboard for deliberate changes. `scripts/configure-monitoring.cjs` reconciles the nine named baseline monitors, alert destination, and retention; rerunning it overwrites those baseline settings but preserves unrelated monitors. Review the script when upgrading Kuma: its Socket.IO interface is version-specific.

Run the helper inside the Kuma container as `node -e <script contents>`, with a private JSON object over stdin containing `username`, `password`, `action`, and `notification` (`url`, `topic`, `username`, `password`). Use `configure` to reconcile, `check` to read sanitized status, or `rehearse` to create a temporary local endpoint and exercise a failure/recovery. Set `bootstrap: true` only for initial account creation; it never resets an existing account. Keep input in the private PC folder and transfer it over SSH; do not paste credentials into shell arguments.

The rehearsal sends real test alerts, takes about three minutes, and removes its temporary monitor on normal completion or a handled error. If the process is killed, remove `Monitoring delivery rehearsal` manually. Confirm exactly one down and one recovery event in ntfy, excluding an optional initial-up event, before relying on delivery. An API delivery check cannot confirm that iOS displayed a lock-screen banner.

## Backup, restore, and maintenance

Run the private `Backup-Cluster.ps1` after configuring Kuma. The worker backup discovers its writable bind mount, pauses this one writer, archives `/srv/swarm`, resumes it, and exports the native AMD64 image. Keep the matching manager backup for Caddy/Authelia configuration and ntfy credentials. Keep the private administrator credential alongside the backup kit.

Restore to a disposable container first, using the same pinned image, UID, SQLite configuration, and data directory. Check database integrity, administrator login, monitor definitions, and notification settings. Keep networking disabled during a restore rehearsal so it cannot duplicate live alerts. Follow [storage recovery](STORAGE.md) and [cluster backups](BACKUPS.md) for node replacement and image restoration.

Before a planned core-service outage, pause affected monitors or use scheduled maintenance. Resume them after recovery. Backup pauses on node 2 also pause monitoring itself; outages during that interval cannot be detected by Kuma. Do not silence a real incident by deleting history or credentials.

## References

- [Kuma 2.5.9 release](https://github.com/louislam/uptime-kuma/releases/tag/2.5.9)
- [Kuma reverse proxy requirements](https://github.com/louislam/uptime-kuma/wiki/Reverse-Proxy)
- [ntfy API subscriptions](https://docs.ntfy.sh/subscribe/api/)
