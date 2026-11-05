# Back up and restore Swarm

Keep all backup files outside Git. Run the full cluster helper in PowerShell:

```powershell
& "C:\Users\Rithvik\Documents\Portfolio-private-backups\Backup-Cluster.ps1" -CheckOnly
& "C:\Users\Rithvik\Documents\Portfolio-private-backups\Backup-Cluster.ps1"
```

Use `Backup-Cluster.ps1 -WorkersOnly` for worker-only snapshots. Keep `Backup-Portfolio.ps1` for manager-only backup and its existing `-Resume` recovery flow. The full cluster command saves a link to the manager snapshot and separate AMD64/ARM64 worker recovery kits.

The preflight leaves services running. A full backup briefly scales the five node-1 services to zero, waits for their writers to stop, archives private state and Caddy certificates, then restores one replica per service. A detached watchdog retries service recovery if the backup worker exits. Image export and download continue after service restart. Use the printed `-Resume` command after an interrupted transfer.

The recovery kit includes `.env.production`, `.auth`, `.portainer`, `.notes`, `.ntfy`, `.swarm`, Caddy data/config volumes, node-1 host configuration, source history plus the current source worktree, Docker image exports, and checksums. Swarm service/node inventory records placement. The app's current and previous images and the worker service images are included from the manager's image cache. Keep explicit tags for every worker image when adding services, and extend coverage before adding worker-local data.

Worker recovery kits include host configuration, partition/LVM inventory, packages, firewall settings, native-platform Docker images, and `/srv/swarm` data. They are recovery archives, not full VM disk images. Read [worker storage and recovery](STORAGE.md) before adding or replacing a stateful worker.

The backup archives contain credentials. Windows ACLs restrict the local folder to your account and SYSTEM; the archives are not password-encrypted. Keep another encrypted/offline copy. The helper validates archive contents, image identities, and checksums; that is not a full restore rehearsal.

## Restore onto replacement hosts

1. Verify `LOCAL-SHA256SUMS.txt` and read the backup's `RESTORE.txt`. Keep the original archive unchanged. Restore into a separate staging directory first.
2. Install compatible Linux/Docker on the replacement AMD manager and worker. Restore source from `source.bundle`, then overlay `source-worktree.tar.gz` to include changes that had not reached Git. Restore the checkout at `/opt/portfolio`, keeping original ownership and permissions.
3. Restore the six private entries from `private-state.tar.gz` together. Create the external Docker volumes `portfolio_caddy_data` and `portfolio_caddy_config`, then extract their matching volume archives into the inspected mountpoints while no service is running. Do not mix database files and encryption keys from different snapshots. Inspect host configuration and restore the required settings deliberately; do not overwrite a replacement host's entire `/etc` blindly.
4. Load `docker-images.tar.gz` on node 1. Load it on node 2 too if registry downloads are unavailable. Initialize a new Swarm using the manager's private IP and join the worker using a fresh token. Restore peer-only firewall rules and labels: `portfolio.data=true` only on node 1 and `portfolio.worker=true` only on node 2. Keep external DNS pointed at the recovered ingress node. Do not copy a live `/var/lib/docker/swarm` directory into a different cluster.
5. The private `.swarm/current.json` points to the saved rendered stack under `.swarm/releases`. Deploy that exact stack with `sudo docker stack deploy --resolve-image never -c /opt/portfolio/.swarm/releases/<saved-release>/stack.json portfolio`. Keep private files and command output out of Git and shared logs. Paths in the saved stack assume `/opt/portfolio`.
6. Run `python3 scripts/swarm-deploy.py check`, `python3 scripts/swarm-portainer.py`, and `python3 scripts/setup-portainer.py --configure`. Check all three nodes, HTTPS, login, writing, and the iPhone subscription. Do not re-enable the retired ARM cron. Take a fresh backup after recovery.

For restoring state onto the current cluster, acquire the deployment lock and scale all five core services to zero first. Wait until their tasks stop before replacing any data. Preserve a recovery copy of the current state. Restore complete directories and certificate volumes from one matched snapshot, then deploy its saved stack and check health. Never start legacy Compose containers alongside Swarm.

## Migration fallback

Keep the private `pre-swarm-*` directory and its original Compose source, container inventory, image-tag inventory, database snapshot, and certificate archives. The original Compose containers have restart disabled. Follow the [Swarm runbook](SWARM.md#roll-back) before using them. The old `backup-private-state.sh` refuses to run on Swarm to prevent an inconsistent live database archive.

## Extend backup coverage for new services

The manager-only backup pauses and archives the five original core services. The cluster helper separately discovers and pauses supported worker writers under `/srv/swarm`. Adding a service to `deploy/swarm-services.json` does not extend that private tool. Its successful completion does not prove a new service's database, external secret, or host bind files were included.

Before storing important data in a new service:

1. Add its Swarm service name and original replica count to the pause/restart/watchdog inventory, or use its documented consistent database-export procedure.
2. Add every persistent bind path or named volume to mount validation, archive creation, checksum verification, and restore instructions. Include `.services/` and `.secrets/` source files if used. Do not archive a live database as ordinary files unless its documentation permits it.
3. Export any external Docker config/secret from its private source or secret manager. `.swarm` contains snapshots of file-backed catalog resources, but cannot reconstruct an external secret's content from Docker inspection.
4. Keep image coverage for current and rollback releases. The renderer tags each current catalog image as `portfolio-<service>:current` on the manager; older untagged catalog versions and non-amd64 platforms may need additional export coverage. The manager exporter remains AMD64-specific; the cluster helper exports each worker's native platform separately.
5. Test restart after partial stop, failed archive and worker termination, then rehearse restoration in a separate environment. Check application data as well as container health.

The private backup implementation lives outside this repository. These Git changes do not modify or deploy it. Keep its updated recovery instructions with the private backup kit. A worker-only stateless service needs no database snapshot, but retain its image/configuration and any host prerequisites.

## Cluster backup completion

A completed cluster folder has `SUCCESS.json` and `LOCAL-SHA256SUMS.txt`. Read `manager-backup.json` for the separately saved manager recovery kit; retain both directories together. Each worker folder has its own manifest, image/data validation report, and transport checksum. `INCOMPLETE.txt` means the cluster backup did not finish. Use `Backup-Cluster.ps1 -Resume "<cluster-folder>"` to reuse completed worker snapshots and continue a partial download; include `-WorkersOnly` for a worker-only run. A failed server snapshot requires investigation and a fresh run, not promotion of its partial archive. Worker snapshots are sequential and do not provide cross-node transactional consistency.

The manager export now includes current/previous release images and their required service images instead of every historical failed-release tag. Optional `.services/` and `.secrets/` source directories are included when present. External secret contents cannot be recovered from Docker inspection; keep their private source material in the recovery kit.
