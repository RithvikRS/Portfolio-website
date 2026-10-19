#!/usr/bin/env bash
# Run as the deployment owner. Archive credentials and databases together.
set -Eeuo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

exec 9>"$(git rev-parse --git-path portfolio-deploy.lock)"
flock -n 9 || { printf 'Wait for the deployment to finish before backing up.\n' >&2; exit 1; }
exec 8>/tmp/ampere-launch.lock
flock -w 600 8 || { printf 'The ARM job is still busy; retry the backup later.\n' >&2; exit 1; }
exec 7>.ntfy/notify.lock
flock -w 60 7 || { printf 'The notifier is still busy; retry the backup later.\n' >&2; exit 1; }

dc() { sudo -n docker compose --env-file .env.production -f compose.production.yaml "$@"; }
backup_parent=/home/opc/.config/portfolio-deploy
mkdir -p -- "$backup_parent"
backup=$(mktemp -d "$backup_parent/private-state-XXXXXXXX")
git rev-parse HEAD > "$backup/source-revision.txt"
running_text="$(dc ps --status running --services app auth portainer ntfy)"
running=()
while IFS= read -r service; do
  [[ -z "$service" ]] || running+=("$service")
done <<< "$running_text"

resume() {
  local result=$?
  trap - EXIT
  if (( ${#running[@]} )); then
    dc start "${running[@]}" || result=1
  fi
  if (( result == 0 )); then
    printf 'Private-state archive: %s/private-state.tar.gz\n' "$backup"
    printf 'Copy this directory to secure storage outside this VM.\n'
  else
    printf 'Backup or restart failed. Treat %s as incomplete and check service health.\n' "$backup" >&2
  fi
  exit "$result"
}
# Register recovery before stop: restart even after a partial stop or failed tar.
trap resume EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
# Stop every writer, including any container caught in a restart loop.
dc stop app auth portainer ntfy
sudo -n tar -czf "$backup/private-state.tar.gz" .env.production .auth .portainer .notes .ntfy
sudo -n chmod 600 "$backup/private-state.tar.gz"
sudo -n tar -tzf "$backup/private-state.tar.gz" > "$backup/inventory.txt"
