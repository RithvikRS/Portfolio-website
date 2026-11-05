# Worker storage and recovery

Keep the five existing core services on AMD node 1. Use worker-local data only for explicitly approved catalog services. This provides persistence and backup recovery, not automatic data failover.

## Storage layout

| Node | Persistent path | Filesystem | Placement |
| --- | --- | --- | --- |
| AMD node 1 | Existing private directories and Caddy volumes | Existing root filesystem | `portfolio.data=true` |
| AMD node 2 | `/srv/swarm/<service>` | Directory on the 30 GiB root filesystem | Exact node ID in `deploy/swarm.json` |
| Ampere A1 | `/srv/swarm/<service>` | Dedicated 40 GiB XFS logical volume | Exact node ID in `deploy/swarm.json` |

Ampere uses `/dev/ocivolume/swarm`, mounted by UUID through `/etc/fstab`. Its root and `/var/oled` filesystems remain unchanged; approximately 3.4 GiB remains free in the volume group. Docker's `swarm-storage.conf` systemd drop-in requires `/srv/swarm` before starting. Do not add `nofail` to this data mount. Worker storage has the persistent SELinux type `container_file_t`; keep SELinux enforcing.

Docker images, container logs, and backup staging still use each node's root filesystem. The new filesystem does not move `/var/lib/docker`. Monitor both root and data capacity. AMD swap is not extra application RAM.

## Add a stateful worker service

1. Choose a node listed in `storage_nodes` in `deploy/swarm.json`. It must be an active worker with `storage.approved=true`. Keep its original compute/worker labels.
2. Create `/srv/swarm/<catalog-service-name>` on that node. Set ownership to the container's documented UID/GID, restrict permissions, and run `sudo restorecon -R /srv/swarm/<service>`. Do not make it world-writable. Preserve `/srv/swarm/.storage-node-id`.
3. Declare long-syntax bind mounts under that service directory. Set one replica, an explicit `node.id == <approved-node-id>` constraint, memory limits, and stop-first update and rollback order. Use application health checks.
4. Add configuration and file-backed secrets through the existing catalog. Keep their private source files in `.secrets/` or `.swarm/`, outside Git. Do not put credentials into the service catalog.
5. Run the private cluster backup preflight and take a backup before relying on the new data. The worker tool discovers running writers, requires one replica pinned to the exact node, pauses them on the manager, waits for their containers to stop, and archives `/srv/swarm` before resuming them. It rejects unaccounted writable bind paths, worker named volumes, and unmanaged writers.
6. Restore the data into a disposable environment and test application-level access before storing important data. For databases spanning multiple services, keep related writers in the same coordinated snapshot. Independent node snapshots are not a distributed transaction backup.

Example catalog service fragment (replace the image, UID/GID, network, and node ID):

```json
{
  "image": "registry.example/application@sha256:<verified-digest>",
  "user": "1000:1000",
  "networks": ["swarm_application"],
  "volumes": [{"type": "bind", "source": "/srv/swarm/application/data", "target": "/data"}],
  "deploy": {
    "replicas": 1,
    "placement": {"constraints": ["node.id == <approved-node-id>"]},
    "resources": {"limits": {"memory": "256M"}},
    "update_config": {"parallelism": 1, "order": "stop-first"},
    "rollback_config": {"parallelism": 1, "order": "stop-first"}
  }
}
```

Use `application` as this fragment's service key so its directory matches the service name. The renderer rejects broad worker-label placement for writable storage, multiple replicas, start-first updates, other services' directories, and traversal outside the approved directory. Existing node-1 storage rules stay available.

## Add or replace a storage worker

Prepare Linux/Docker, peer firewall rules, and Swarm membership first. Provision and mount its data filesystem; configure mount dependencies and SELinux before starting services. Give the node `storage.approved=true`, then record its exact node ID and `/srv/swarm` root in `deploy/swarm.json`.

Update the private PC `backup-settings.json` workers list with its name, SSH host, and node ID. Verify its SSH host key through a trusted connection. Update `/srv/swarm/.storage-node-id` after restoring onto a replacement node. Restore data ownership, permissions, and SELinux labels before updating service placement to that new ID.

Never reuse `portfolio.data=true` for a worker. Do not change placement to a different empty node to make a failed stateful service start.

## Run backups

Use the private `Backup-Cluster.ps1` entry point described in [BACKUPS.md](BACKUPS.md). Keep that script, configuration, snapshots, and recovery credentials on the PC outside Git. Run a fresh cluster backup after adding storage or changing host configuration.

The manager backup and worker snapshots run sequentially. A worker backup pauses only its discovered stateful services. An independent manager watchdog restores original replica counts if the pause controller exits; its 20-minute lease also expires if the PC disappears. Failed archive or recovery checks leave the run incomplete. Check saved job metadata before retrying an interrupted worker run; do not treat a partial download as a successful backup.

## Restore a worker

1. Verify the saved checksums and image inventory. Keep the original archives unchanged.
2. Rebuild a compatible worker, prepare `/srv/swarm`, and restore selected host settings deliberately. Do not overwrite an entire replacement `/etc` or copy live Swarm daemon state.
3. Keep its application services scaled to zero. Extract `worker-data.tar.gz` into `/srv/swarm` with numeric ownership, ACLs, and extended attributes, then run `restorecon -R /srv/swarm`. Do not overlay a live database.
4. Load that worker's `docker-images.tar.gz` on the matching architecture. Restore file-backed secrets and configuration from the manager's matched recovery kit. Encrypted application data requires its matching keys.
5. Join the cluster using a fresh token, restore approved labels, and update exact node IDs and the storage marker. Restore the saved service specifications with the correct replica counts.
6. Check application data, login, attachments, HTTP health, and Portainer. Retain the old data until recovery checks pass.

A checksum check and SQLite restore exercise do not prove a full VM, PostgreSQL, or future application's recovery. Add each application's restore rehearsal when deploying it.