# Back up and restore private state

Run these commands in the AMD server's Bash SSH session as `opc`. Keep backups private and copy them to encrypted storage outside the VM. Never commit an archive, credential file, or backup inventory to Git.

## Create an archive

Pause manual setup, credential changes, and notification tests while taking a backup. Run:

```sh
cd /opt/portfolio
bash scripts/backup-private-state.sh
sudo docker compose --env-file .env.production -f compose.production.yaml ps
python3 scripts/setup-ntfy.py check
```

The helper takes the deployment lock, waits up to ten minutes for the active ARM attempt, and locks the notifier. Scheduled ARM attempts skip while its lock is held. It stops all four state-writing services (`app`, `auth`, `portainer`, and `ntfy`), including containers in a restart loop, then archives these paths together:

| Path | Preserve together |
| --- | --- |
| `.env.production` | Domains, mail configuration, and runtime settings |
| `.auth/` | Accounts, encryption/signing keys, and matching database |
| `.portainer/` | Recovery password, OAuth credentials, and database |
| `.notes/` | Drafts, published snapshots, revisions, and trash |
| `.ntfy/` | Account credentials, login sheet, SQLite databases/cache, pending alerts, and delivery history |

Expect a brief public-site interruption and an expired Authelia session. The helper restarts only services that were running beforehand, including after a partial stop or archive failure. A restart failure returns an error; inspect `compose ps` and restore service health before leaving SSH. SIGKILL, VM loss, or power loss cannot run the recovery trap.

Find the archive, source revision, and inventory in the printed `/home/opc/.config/portfolio-deploy/private-state-*` directory. Its mode is 700 and the archive is 600. The archive may be root-owned; use `sudo` for access without making it public. Treat a failed run's directory as incomplete. Copy a successful backup off the VM through a private transfer and verify that you can read it there.

This archive covers application state. For full VM recovery, also preserve the matching Git revision and compatible images, Caddy's `caddy_data` and `caddy_config` named volumes, private OCI configuration/API keys, `/home/opc/ampere-env.sh`, the ARM public key, the provisioning launcher, and `crontab -l`. Store the ARM SSH private key separately in your password manager or encrypted backup. Do not add these host credentials to the repository. Back up Caddy volumes separately while Caddy is stopped; inspect the actual Compose volume names first.

## Restore a matching snapshot

1. Stop PR merges/deployments and manual setup/notifier commands. Create a fresh recovery archive of the current state first. Keep it outside the directories you will replace.
2. Read `source-revision.txt` and `inventory.txt`. Use a trusted archive from your own backup. Inspect it with `sudo tar -tzf /absolute/path/private-state.tar.gz`. Confirm that all five private directories/settings entries above are present. Extract into a new private staging directory, never directly over the live checkout:

   ```sh
   umask 077
   stage=$(mktemp -d /home/opc/.config/portfolio-deploy/restore-XXXXXXXX)
   sudo tar --extract --gzip --same-owner --same-permissions \
     --file /absolute/path/private-state.tar.gz --directory "$stage"
   ```

3. In the same SSH session, run `export stage` followed by `bash` to open a temporary shell, then acquire the locks below. Keep this shell open throughout replacement and restart. If any lock fails, it exits; stop and retry later rather than continuing unlocked.

   ```sh
   cd /opt/portfolio
   exec 9>"$(git rev-parse --git-path portfolio-deploy.lock)"
   flock -n 9 || exit 1
   exec 8>/tmp/ampere-launch.lock
   flock -w 600 8 || exit 1
   exec 7>.ntfy/notify.lock
   flock -w 60 7 || exit 1
   dc() { sudo docker compose --env-file .env.production -f compose.production.yaml "$@"; }
   dc stop app auth portainer ntfy || exit 1
   ```

4. Preserve the current `.env.production`, `.auth`, `.portainer`, `.notes`, and `.ntfy` as separate recovery copies. Replace each with its staged counterpart as a complete unit, keeping owners and modes. Do not overlay files: extra notes could remain published, and mixed credentials/database versions can break login. Restore the entire `.ntfy` directory, including pending alerts and cooldown history, so changing servers does not reset notification suppression. Keep manual notifier commands paused while replacing its lock file.
5. Use the source/Compose configuration and images compatible with the snapshot. An app image rollback alone does not restore configuration or state. Start the four services with `dc up --no-build -d --force-recreate --wait --wait-timeout 180 app auth portainer ntfy`, then reload Caddy if you restored its configuration. On a failed restore, keep the current-state recovery copy available and repair or restore that matched set before resuming traffic. Do not run setup against an empty or half-restored private directory.
6. Check `dc ps`, run `python3 scripts/setup-ntfy.py check`, sign in through the dashboard and Portainer, and check draft/public writing visibility. Inspect Oracle instances before re-enabling a saved provisioning cron entry. A pending alert in an older snapshot can be delivered again. Run `exit` after completing recovery and checks to release the locks and return to your original SSH shell.

For an app-only rollback with unchanged data/configuration, use the [image rollback runbook](DOCKER.md#roll-back-an-app-deployment).

## Check the backup procedure locally

Run `python3 -m unittest discover -s tests -p 'test_private_backup.py'` on Linux. The tests use disposable files and fake Docker commands to check archive inventory, restored contents/modes, writer locks, and service restart after failures. They do not read production credentials or stop real containers. Check an actual backup on a separate recovery host before relying on it for a full VM migration.
