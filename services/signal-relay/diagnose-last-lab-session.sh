#!/bin/sh
set -eu

session_id=$(docker compose logs --no-log-prefix signal-relay | sed -n 's|.*POST /v1/lab/sessions/\([^/]*\)/messages.*|\1|p' | tail -n 1)

if [ -z "$session_id" ]; then
  echo "No lab message session was found in the relay logs." >&2
  exit 1
fi

printf 'Latest session: %s\n' "$session_id"
docker inspect reticulum-relay --format 'Relay image: {{.Image}} created={{.Created}}'
curl -fsS "http://127.0.0.1:8080/v1/lab/sessions/$session_id"
printf '\n\nDelivery correlation log:\n'
docker compose logs --no-log-prefix --since=5m signal-relay | grep 'LXMF delivery received' || true