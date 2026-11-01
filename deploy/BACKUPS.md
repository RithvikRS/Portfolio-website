# Back up and restore Swarm

Keep all backup files outside Git. Run the private PC helper in PowerShell:

```powershell
& "C:\Users\Rithvik\Documents\Portfolio-private-backups\Backup-Portfolio.ps1" -CheckOnly
& "C:\Users\Rithvik\Documents\Portfolio-private-backups\Backup-Portfolio.ps1"
```

The preflight leaves services running. A full backup briefly scales the five node-1 services to zero, waits for their writers to stop, archives private state and Caddy certificates, then restores one replica per service. A detached watchdog retries service recovery if the backup worker exits. Image export and download continue after service restart. Use the printed `-Resume` command after an interrupted transfer.

The recovery kit includes `.env.production`, `.auth`, `.portainer`, `.notes`, `.ntfy`, `.swarm`, Caddy data/config volumes, node-1 host configuration, source history plus the current source worktree, Docker image exports, and checksums. Swarm service/node inventory records placement. The app's current and previous images and the worker service images are included from the manager's image cache. Keep explicit tags for every worker image when adding services, and extend coverage before adding worker-local data.

The reusable full backup covers the manager's host configuration; it does not archive node 2's operating system. Node 2 currently has no application data: rebuild its OS/Docker, rejoin it to Swarm, restore peer firewall rules, and apply the worker label. Preserve any future node-2 host customization separately. The migration recovery folder also contains its original container inventory.

The backup archives contain credentials. Windows ACLs restrict the local folder to your account and SYSTEM; the archives are not password-encrypted. Keep another encrypted/offline copy. The helper validates archive contents, image identities, and checksums; that is not a full restore rehearsal.

## Restore onto replacement hosts

1. Verify `LOCAL-SHA256SUMS.txt` and read the backup's `RESTORE.txt`. Keep the original archive unchanged. Restore into a separate staging directory first.
2. Install compatible Linux/Docker on the replacement AMD manager and worker. Restore source from `source.bundle`, then overlay `source-worktree.tar.gz` to include changes that had not reached Git. Restore the checkout at `/opt/portfolio`, keeping original ownership and permissions.
3. Restore the six private entries from `private-state.tar.gz` together. Create the external Docker volumes `portfolio_caddy_data` and `portfolio_caddy_config`, then extract their matching volume archives into the inspected mountpoints while no service is running. Do not mix database files and encryption keys from different snapshots. Inspect host configuration and restore the required settings deliberately; do not overwrite a replacement host's entire `/etc` blindly.
4. Load `docker-images.tar.gz` on node 1. Load it on node 2 too if registry downloads are unavailable. Initialize a new Swarm using the manager's private IP and join the worker using a fresh token. Restore peer-only firewall rules and labels: `portfolio.data=true` only on node 1 and `portfolio.worker=true` only on node 2. Keep external DNS pointed at the recovered ingress node. Do not copy a live `/var/lib/docker/swarm` directory into a different cluster.
5. The private `.swarm/current.json` points to the saved rendered stack under `.swarm/releases`. Deploy that exact stack with `sudo docker stack deploy --resolve-image never -c /opt/portfolio/.swarm/releases/<saved-release>/stack.json portfolio`. Keep private files and command output out of Git and shared logs. Paths in the saved stack assume `/opt/portfolio`.
6. Run `python3 scripts/swarm-deploy.py check`, `python3 scripts/swarm-portainer.py`, and `python3 scripts/setup-portainer.py --configure`. Check both nodes, HTTPS, login, writing, and the iPhone subscription. Do not re-enable the retired ARM cron. Take a fresh backup after recovery.

For restoring state onto the current cluster, acquire the deployment lock and scale all five core services to zero first. Wait until their tasks stop before replacing any data. Preserve a recovery copy of the current state. Restore complete directories and certificate volumes from one matched snapshot, then deploy its saved stack and check health. Never start legacy Compose containers alongside Swarm.

## Migration fallback

Keep the private `pre-swarm-*` directory and its original Compose source, container inventory, image-tag inventory, database snapshot, and certificate archives. The original Compose containers have restart disabled. Follow the [Swarm runbook](SWARM.md#roll-back) before using them. The old `backup-private-state.sh` refuses to run on Swarm to prevent an inconsistent live database archive.
