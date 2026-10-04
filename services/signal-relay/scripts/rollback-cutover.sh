#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 && "$1" == "--confirm" ]] || { printf 'Usage: %s --confirm\n' "$0" >&2; exit 2; }
service_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
deploy_root=${SIGNAL_RELAY_DEPLOY_ROOT:-/opt/signal-relay}
backup_root=/opt/migration-backups/rollback-signal-relay-$(date +%F-%H%M%S)

sudo install -d -m 0700 "$backup_root"
sudo docker compose -f "$deploy_root/compose.yaml" --env-file "$deploy_root/.env" stop signal-relay
sudo tar --xattrs --acls -C "$deploy_root" -czf "$backup_root/config-before-rollback.tgz" .env reticulum lab-sender-reticulum
sudo rsync -aHAX --delete "$deploy_root/reticulum/" "$service_root/reticulum/"
sudo rsync -aHAX --delete "$deploy_root/lab-sender-reticulum/" "$service_root/lab-sender-reticulum/"
sudo install -m 0600 "$deploy_root/.env" "$service_root/.env"
sudo docker compose -f "$deploy_root/compose.yaml" --env-file "$deploy_root/.env" rm -f signal-relay
sudo docker compose -f "$service_root/compose.yaml" up -d --wait --wait-timeout 60 --no-deps signal-relay
printf 'Restored Signal Relay source deployment. Backup: %s\n' "$backup_root"