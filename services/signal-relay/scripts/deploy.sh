#!/usr/bin/env bash
set -euo pipefail

service_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
deploy_root=${SIGNAL_RELAY_DEPLOY_ROOT:-/opt/signal-relay}
deploy_compose="$deploy_root/compose.yaml"

"$service_root/scripts/preflight.sh"
active_config=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' reticulum-relay)
[[ "$active_config" == "$deploy_compose" ]] || {
  printf 'ERROR: relay is not deployed from %s\n' "$deploy_root" >&2
  exit 1
}

install -m 0644 "$service_root/compose.yaml" "$deploy_compose"
docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" config --quiet
docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" pull signal-relay
docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" up -d --wait --wait-timeout 60 --no-deps signal-relay
docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" ps signal-relay