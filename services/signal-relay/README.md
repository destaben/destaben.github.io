# Reticulum Contact

Self-hosted FastAPI/LXMF bridge for the public Reticulum contact point. It is intentionally separate from the Astro site: GitHub Pages cannot run persistent APIs or WebSockets. Nginx and the outbound Cloudflare Tunnel are maintained separately in [`destaben/lab-inverse-proxy`](https://github.com/destaben/lab-inverse-proxy).

## Local demo

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
cp .env.example .env
.venv/bin/uvicorn signal_relay.app:app --host 127.0.0.1 --port 8787
```

The default `demo` mode is an explicitly labelled local acknowledgement loop. It exercises HTTP, WebSocket, input validation, and rate limiting without claiming to send Reticulum traffic.

## Reticulum mode

Set `SIGNAL_RELAY_MODE=reticulum` and optionally `SIGNAL_RELAY_RETICULUM_CONFIG_DIR` to initialise the official `rns` runtime. The service persists a private delivery identity under `SIGNAL_RELAY_STORAGE_DIR`, announces its LXMF destination hash, and retains the newest 20 message bodies as bounded plain text. Keep its storage and service configuration outside Git.

The default Reticulum configuration uses outbound `TCPClientInterface` bootstrap transports, which work behind CGNAT because the relay initiates connections. Use `reticulum-config.example` as the starter, do not expose a Reticulum TCP port, and never add a `TCPServerInterface`. Cloudflare Tunnel carries HTTP only through the separately deployed edge.

`GET /v1/lab/reticulum-nodes` reports configured public aliases, deliberately published `tcp://host:port` endpoints, and `up` or `down` connection states. Set `SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES` to a private JSON mapping from TCP client interface names to public aliases, then set `SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS` to a private JSON mapping from those aliases to their intentionally public TCP URLs. Both maps must define the same aliases. Keep both mappings only in the deployment `.env`; they default to `{}`. The endpoint never returns interface names, and each URL must have a host and explicit port without credentials, paths, queries, fragments, stray `?` or `#` even when empty, non-ASCII, invisible, whitespace or control characters, or percent-escapes (the URL must be printable ASCII), non-global literal IP addresses, IPv4-embedding IPv6 addresses (NAT64 `64:ff9b::/96` and `64:ff9b:1::/48`, IPv4-compatible `::/96`, 6to4 `2002::/16`, and Teredo `2001::/32`), IPv6 that is not bracketed (bare IPv6 and bracketed IPv4 are rejected), non-canonical IPv4 spellings such as `127.1` or `0x7f.1`, single-label hostnames or private-use hostname suffixes such as `.lan`, `.local`, `.internal` and `.home.arpa`, and empty labels including a trailing dot.

## Optional integrations

Telegram notifications require both `SIGNAL_RELAY_TELEGRAM_BOT_TOKEN` and `SIGNAL_RELAY_TELEGRAM_CHAT_ID` in the private environment. Never commit them. Each received LXMF message is stored before notification, so notification failure never interrupts delivery.

The educational Reticulum session is disabled by default. Enable it only with a separate, reachable sender configuration and a verified external route. The reverse-proxy repository owns its public request limits; it bounds public reads per client IP and applies a stricter limit to laboratory POSTs. The static portfolio remains an anonymous consumer: do not add a browser API key, because every visitor could extract it. Responses expose only the documented opaque ID, state, bounded error code, expiry, and public node alias.

The Home Assistant lab is a fixed read-only projection. Configure a dedicated token and only the three required sensor entity IDs in the private relay `.env`. Every entity ID must be a lowercase `domain.object_id` value using only letters, digits, and underscores; startup fails on an invalid ID with an error that names the setting but never echoes the value. Successful Home Assistant projections are cached for the configured window, which is never below 900 seconds. A failed refresh is remembered for 30 seconds, so an outage is not retried on every public request, and concurrent requests at cache expiry share one upstream refresh. No new Home Assistant read starts once a refresh is 10 seconds old, and each read times out after 5 seconds, so one refresh is bounded at about 15 seconds; concurrent callers wait on that single refresh, and fresh cache hits never wait on a refresh, and redirects are never followed, so the Bearer token is never sent to another location. The `/v1/lab/home-status` route returns `503 home_status_unavailable` for a null, boolean, or non-numeric state.

The optional Meshtastic status panel uses that same token and the `SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS` map described below, reading only its `gateway`, `nodes_online`, and `nodes_total` entries; all three must be present before `GET /v1/lab/meshtastic-status` can be available. `SIGNAL_RELAY_MESHTASTIC_LAST_NODE_ENTITY_ID` is optional and must resolve to a deliberately selected name-only state suitable for publication. Keep `SIGNAL_RELAY_MESHTASTIC_STATUS_CACHE_SECONDS` at 900 seconds or higher. The route returns only availability, aggregate online and total counts, an optional latest-node name, and refresh time; it returns `503 meshtastic_status_unavailable` when it cannot form that projection. Counts must be non-negative whole numbers, online nodes cannot exceed total nodes, and the gateway must report `Connected`, the same state the send projection requires. The optional `lastNode` is omitted, without failing the panel, when its state is a Home Assistant placeholder (`unavailable`, `unknown`, `none`, or empty), is not printable text, or is longer than 64 characters after whitespace normalization. A missing entity (HTTP 404) also omits it. Other HTTP errors (such as 401 or 500) and transport errors still make the route return `503 meshtastic_status_unavailable`. Nginx reaches Home Assistant through its unexposed internal listener; neither Home Assistant nor its credentials receive a public route. The status route is read-only; the send route is described below. Use [docs/MESHTASTIC-INVENTORY.md](../../docs/MESHTASTIC-INVENTORY.md) to discover candidate entities and verify the deployed projection without disclosing them.

The Meshtastic lab adds a fixed Home Assistant projection (`GET /v1/lab/meshtastic`) and an optional public MediumFast broadcast. Configure `SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS` as a private JSON map with these required keys: `gateway`, `node_long_name`, `node_short_name`, `uptime_seconds`, `battery_percent`, `voltage`, `channel_utilization_percent`, `airtime_tx_percent`, `nodes_online`, `nodes_total`, `packets_rx`, `packets_tx`, `packets_rx_bad`, `packets_rx_duplicate`, `packets_tx_relayed`, `packets_tx_relay_cancelled`, `rx_per_minute`, `tx_per_minute`, `rf_errors_per_minute`, `duplicates_per_minute`, `relay_cancelled_per_minute`, and `recent_activity_1` through `recent_activity_5`. Values are private HA entity IDs and stay only in `.env`. The relay publishes only those five sanitized MediumFast records, newest first; it does not enumerate nodes or expose IDs, positions, routes, raw attributes, or other message history. Set `SIGNAL_RELAY_MESHTASTIC_TURNSTILE_SECRET` to enable the public broadcast endpoint. Create a managed Cloudflare Turnstile widget for `info.destaben.dev`, add its site key to the GitHub Actions variable `TURNSTILE_SITE_KEY`, and enter its secret only in the deployment `.env`. The relay validates the Turnstile response, applies a cooldown, and invokes only `script.meshtastic_public_broadcast`; it cannot select a different channel or any other HA service.

## Container deployment

GitHub Actions publishes `ghcr.io/destaben/signal-relay:latest` for `linux/amd64` and `linux/arm64`. Deploy this Compose file in a private directory with its `.env`, `reticulum/`, and optional `lab-sender-reticulum/` configuration:

```sh
mkdir -p /opt/signal-relay/reticulum /opt/signal-relay/lab-sender-reticulum
cd /opt/signal-relay
curl -fsSLo compose.yaml https://raw.githubusercontent.com/destaben/destaben.github.io/main/services/signal-relay/compose.yaml
curl -fsSLo .env https://raw.githubusercontent.com/destaben/destaben.github.io/main/services/signal-relay/.env.example
curl -fsSLo reticulum/config https://raw.githubusercontent.com/destaben/destaben.github.io/main/services/signal-relay/reticulum-config.example
chmod 600 .env
sudo chown 10001:10001 reticulum lab-sender-reticulum
docker network create destaben-edge
docker compose config
docker compose pull
docker compose up -d
```

The relay has no host port and joins the external `destaben-edge` network. Deploy and operate Nginx and Cloudflare Tunnel from [`destaben/lab-inverse-proxy`](https://github.com/destaben/lab-inverse-proxy); start the edge after the relay has joined the shared network. Public `/v1/lab/*` routes, including `GET /v1/lab/meshtastic-status`, need their allowlist entries in that repository; the Meshtastic entry is in `destaben/lab-inverse-proxy` PR #7. The edge places Cloudflared on an isolated internal ingress network and does not attach it to `destaben-edge`. Before deploying the edge, check that its reserved `172.30.250.0/29` subnet does not overlap Docker, LAN, or VPN networks. Do not replace `.env`, `reticulum/`, `lab-sender-reticulum/`, or the `signal-relay-data` volume during updates: they hold secrets and persistent identities.

When public bootstrap transports change, manually merge their interface entries from `reticulum-config.example` into the private `reticulum/config`. Do not replace the Reticulum directory wholesale. If the relay cannot parse its configuration, inspect `reticulum/config`, ensure it has `[reticulum]` and `[interfaces]` root sections, then run `docker compose config` and recreate only `signal-relay`.

## Host redeployment

The versioned source checkout belongs at `/opt/src/destaben.github.io`; the live deployment belongs in `/opt/signal-relay`. The private `.env`, `reticulum/`, `lab-sender-reticulum/`, and `signal-relay-data` volume are state and are never copied into Git. Daily operations require a user in the `docker` group with `docker context show` set to `default`; the scripts do not use `sudo`.

```sh
services/signal-relay/scripts/preflight.sh
services/signal-relay/scripts/deploy.sh
services/signal-relay/scripts/verify.sh
```

For a configuration-only rollback after the cutover, with a clean Git worktree:

```sh
services/signal-relay/scripts/rollback.sh --confirm <git-ref>
```

No redeployment script runs `docker compose down`, publishes port `8787`, replaces `.env`, or recreates the persistent data volume. The completed migration to `/opt/signal-relay` is not reversible through a repository script; recover the active deployment from the tracked configuration and approved private backups.

## Tests

```sh
.venv/bin/python -m pytest
```

## End-to-end verification

Run the portfolio and bridge locally in separate terminals, then open `http://127.0.0.1:4321`:

```sh
# Repository root
npm run dev -- --host 127.0.0.1 --port 4321

# services/signal-relay
SIGNAL_RELAY_MODE=reticulum .venv/bin/uvicorn signal_relay.app:app --host 127.0.0.1 --port 8787
```

The contact panel fetches the local bridge on local hosts. To preview an arrival notice without sending real LXMF traffic, start demo mode and use `POST /v1/demo/inbox`; the endpoint returns `404` in Reticulum mode.
