#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 2 && "$1" == "--confirm" ]] || {
  printf 'Usage: %s --confirm <git-ref>\n' "$0" >&2
  exit 2
}

target_ref=$2
service_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
deploy_root=${SIGNAL_RELAY_DEPLOY_ROOT:-/opt/signal-relay}
deploy_compose="$deploy_root/compose.yaml"
cd "$service_root"

git diff --quiet || {
  printf 'ERROR: working tree has changes; commit or stash them before rollback\n' >&2
  exit 1
}
git rev-parse --verify --quiet "$target_ref^{commit}" >/dev/null || {
  printf 'ERROR: unknown Git reference: %s\n' "$target_ref" >&2
  exit 1
}
git show "$target_ref:services/signal-relay/compose.yaml" > "$deploy_compose"
docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" config --quiet
docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" up -d --no-deps signal-relay
"$service_root/scripts/verify.sh"
printf 'Rolled back relay Compose configuration to %s. Identities, data and .env were unchanged.\n' "$target_ref"