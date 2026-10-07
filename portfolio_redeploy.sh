#!/usr/bin/env bash
set -Eeuo pipefail

# Keep the function loaded while Git updates this script on disk.
main() {
  local pull_changes=true
  case "${1:-}" in
    '') ;;
    --no-pull) pull_changes=false ;;
    *) printf 'Usage: bash portfolio_redeploy.sh [--no-pull]\n' >&2; return 2 ;;
  esac
  if (( $# > 1 )); then
    printf 'Usage: bash portfolio_redeploy.sh [--no-pull]\n' >&2
    return 2
  fi

  local repo_dir
  repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$repo_dir"
  local tool
  for tool in git docker flock curl; do
    command -v "$tool" >/dev/null || { printf 'Missing required command: %s\n' "$tool" >&2; return 1; }
  done
  exec 9>"$(git rev-parse --git-path portfolio-deploy.lock)"
  flock -n 9 || { printf 'Another portfolio deployment is running.\n' >&2; return 1; }

  if [[ ! -f .env.production ]]; then
    printf 'Create .env.production with the domain and email settings before deploying.\n' >&2
    return 1
  fi
  if git ls-files --error-unmatch -- .env.production >/dev/null 2>&1; then
    printf '.env.production must remain private and untracked by Git.\n' >&2
    return 1
  fi
  chmod 600 .env.production

  local -a docker_cmd=(docker)
  if ! docker info >/dev/null 2>&1; then
    sudo -n docker info >/dev/null 2>&1 || { printf 'Docker is unavailable; check the service and sudo access.\n' >&2; return 1; }
    docker_cmd=(sudo -n docker)
  fi

  if "$pull_changes"; then
    printf 'Fetching the latest main branch...\n'
    git fetch origin '+refs/heads/main:refs/remotes/origin/main'
    if [[ "$(git branch --show-current)" != main ]]; then
      printf 'The server checkout must be on main. Resolve any local changes before switching branches.\n' >&2
      return 1
    fi
    if ! git merge-base --is-ancestor HEAD refs/remotes/origin/main; then
      printf 'The server has commits outside origin/main. Reconcile them before deploying.\n' >&2
      return 1
    fi

    # The initial deployment copied files before they were committed locally.
    # Back them up only when their contents already match the pushed version.
    local -a changed_files=()
    local file expected actual
    while IFS= read -r -d '' file; do changed_files+=("$file"); done < <(
      git diff --name-only -z HEAD --
      git ls-files --others --exclude-standard -z
    )
    for file in "${changed_files[@]}"; do
      expected="$(git rev-parse --verify "refs/remotes/origin/main:$file" 2>/dev/null || true)"
      actual=''
      if [[ -f "$file" && ! -L "$file" ]]; then
        actual="$(git hash-object --path="$file" -- "$file")"
      fi
      if [[ -z "$actual" || "$actual" != "$expected" ]]; then
        printf 'Server changes differ from origin/main: %s\nCommit and merge the corresponding changes locally, or reconcile this server file before retrying.\n' "$file" >&2
        return 1
      fi
    done
    if (( ${#changed_files[@]} )); then
      git -c user.name='Portfolio deployment' -c user.email='portfolio-deployment@localhost' \
        stash push --include-untracked -m "Deployment files already in origin/main $(date -u +%Y%m%dT%H%M%SZ)"
      printf 'Matching server copies were saved in git stash; private environment files stay in place.\n'
    fi
    git merge --ff-only refs/remotes/origin/main
  else
    printf 'Using the existing server checkout without pulling Git changes.\n'
  fi

  local -a compose=("${docker_cmd[@]}" compose --env-file .env.production -f compose.production.yaml)
  printf 'Validating the production configuration...\n'
  "${compose[@]}" config --quiet
  # Caddy has a fixed backend IP, so a second Compose container would conflict.
  "${compose[@]}" exec -T caddy caddy validate \
    --config /etc/caddy/Caddyfile --adapter caddyfile </dev/null

  printf 'Building the app, generated pages, link checks, and tests...\n'
  "${compose[@]}" build app </dev/null
  printf 'Starting the production stack and waiting for app health...\n'
  "${compose[@]}" up --no-build -d --wait --wait-timeout 180 </dev/null
  # A changed bind-mounted Caddyfile does not itself recreate the container.
  "${compose[@]}" exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile </dev/null

  local domain
  domain="$("${compose[@]}" exec -T caddy sh -c 'printf "%s" "$DOMAIN"' </dev/null)"
  [[ -n "$domain" ]] || { printf 'The Caddy hostname is missing.\n' >&2; return 1; }
  printf 'Checking https://%s/ ...\n' "$domain"
  curl --fail --silent --show-error --retry 3 --retry-delay 2 --retry-connrefused \
    --connect-timeout 10 --max-time 30 --output /dev/null "https://$domain/"
  printf 'Contact API: '
  curl --fail --silent --show-error --retry 3 --retry-delay 2 --retry-connrefused \
    --connect-timeout 10 --max-time 30 "https://$domain/api/contact"
  printf '\n'
  "${compose[@]}" ps
  printf 'Deployed main commit %s at https://%s/\n' "$(git rev-parse --short HEAD)" "$domain"
}

trap 'printf "Deployment stopped at line %s. Review the error above before retrying.\n" "$LINENO" >&2' ERR
main "$@"
