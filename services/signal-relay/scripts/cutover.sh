#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 && "$1" == "--confirm" ]] || {
  printf 'Usage: %s --confirm\n' "$0" >&2
  exit 2
}

service_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
deploy_root=${SIGNAL_RELAY_DEPLOY_ROOT:-/opt/signal-relay}
source_compose="$service_root/compose.yaml"
deploy_compose="$deploy_root/compose.yaml"

"$service_root/scripts/preflight.sh"
active_config=$(sudo docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' reticulum-relay)
[[ "$active_config" == "$source_compose" ]] || {
  printf 'ERROR: cutover requires relay to run from %s\n' "$source_compose" >&2
  exit 1
}

rollback_source() {
  sudo docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" rm -sf signal-relay || true
  sudo docker compose -f "$source_compose" up -d --no-deps signal-relay || true
}
trap rollback_source ERR

sudo docker compose -f "$source_compose" stop signal-relay
sudo install -D -m 0600 "$service_root/.env" "$deploy_root/.env"
sudo rsync -aHAX --delete "$service_root/reticulum/" "$deploy_root/reticulum/"
sudo rsync -aHAX --delete "$service_root/lab-sender-reticulum/" "$deploy_root/lab-sender-reticulum/"
sudo chown -R 10001:10001 "$deploy_root/reticulum" "$deploy_root/lab-sender-reticulum"
sudo install -m 0644 "$source_compose" "$deploy_compose"
sudo docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" config --quiet
sudo docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" up -d --wait --wait-timeout 60 --no-deps signal-relay
trap - ERR
"$service_root/scripts/verify.sh"
printf 'Relay cutover completed. The source directory remains available for rollback.\n'