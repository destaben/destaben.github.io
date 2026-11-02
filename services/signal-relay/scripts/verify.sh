#!/usr/bin/env bash
set -euo pipefail

service_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
deploy_root=${SIGNAL_RELAY_DEPLOY_ROOT:-/opt/signal-relay}
deploy_compose="$deploy_root/compose.yaml"

[[ $(docker inspect --format '{{.State.Running}}' reticulum-relay) == "true" ]] || {
  printf 'ERROR: reticulum-relay is not running\n' >&2
  exit 1
}
[[ $(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' reticulum-relay) == "$deploy_compose" ]] || {
  printf 'ERROR: relay is not deployed from %s\n' "$deploy_root" >&2
  exit 1
}
docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' reticulum-relay | grep -qx healthy
docker compose -f "$deploy_compose" --env-file "$deploy_root/.env" ps signal-relay
if ss -ltn '( sport = :8787 )' | grep -q LISTEN; then
  printf 'ERROR: relay HTTP port 8787 is published on the host\n' >&2
  exit 1
fi
printf 'Relay verification passed. Run edge acceptance checks separately.\n'