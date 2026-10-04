#!/usr/bin/env bash
set -euo pipefail

service_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
deploy_root=${SIGNAL_RELAY_DEPLOY_ROOT:-/opt/signal-relay}
deploy_compose="$deploy_root/compose.yaml"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -f "$service_root/compose.yaml" ]] || fail "source Compose file not found"
[[ -f "$deploy_compose" ]] || fail "deployment Compose file not found: $deploy_compose"
[[ -f "$deploy_root/.env" ]] || fail "deployment environment file not found: $deploy_root/.env"
[[ -d "$deploy_root/reticulum" ]] || fail "Reticulum configuration directory not found"
[[ -d "$deploy_root/lab-sender-reticulum" ]] || fail "lab sender configuration directory not found"

docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" config --quiet
docker network inspect destaben-edge >/dev/null

active_config=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' reticulum-relay 2>/dev/null || true)
case "$active_config" in
  "$service_root/compose.yaml")
    printf 'Preflight passed. Relay runs from the source checkout.\n'
    ;;
  "$deploy_compose")
    printf 'Preflight passed. Relay runs from %s.\n' "$deploy_root"
    ;;
  *)
    fail "relay uses an unexpected Compose file: ${active_config:-not running}"
    ;;
esac