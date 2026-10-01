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

`GET /v1/lab/reticulum-nodes` reports configured public aliases, deliberately published `tcp://host:port` endpoints, and `up` or `down` connection states. Set `SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES` to a private JSON mapping from TCP client interface names to public aliases, then set `SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS` to a private JSON mapping from those aliases to their intentionally public TCP URLs. Both maps must define the same aliases. Keep both mappings only in the deployment `.env`; they default to `{}`. The endpoint never returns interface names, and each URL must have a host and explicit port without credentials, paths, queries, fragments or private literal IP addresses.

## Optional integrations

Telegram notifications require both `SIGNAL_RELAY_TELEGRAM_BOT_TOKEN` and `SIGNAL_RELAY_TELEGRAM_CHAT_ID` in the private environment. Never commit them. Each received LXMF message is stored before notification, so notification failure never interrupts delivery.

The educational Reticulum session is disabled by default. Enable it only with a separate, reachable sender configuration and a verified external route. The reverse-proxy repository owns its public request limits; it bounds public reads per client IP and applies a stricter limit to laboratory POSTs. The static portfolio remains an anonymous consumer: do not add a browser API key, because every visitor could extract it. Responses expose only the documented opaque ID, state, bounded error code, expiry, and public node alias.

The Home Assistant lab is a fixed read-only projection. Configure a dedicated token and only the three required sensor entity IDs in the private relay `.env`. Nginx reaches Home Assistant through its unexposed internal listener; neither Home Assistant nor its credentials receive a public route.

The Meshtastic lab adds a second, fixed Home Assistant projection and an optional public MediumFast broadcast. Configure `SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS` as a private JSON map with exactly these keys: `gateway`, `node_long_name`, `node_short_name`, `uptime_seconds`, `battery_percent`, `voltage`, `channel_utilization_percent`, `airtime_tx_percent`, `nodes_online`, `nodes_total`, `packets_rx`, `packets_tx`, `packets_rx_bad`, `packets_rx_duplicate`, `packets_tx_relayed`, `packets_tx_relay_cancelled`, `rx_per_minute`, `tx_per_minute`, `rf_errors_per_minute`, `duplicates_per_minute`, `relay_cancelled_per_minute`, `last_message`, `last_sender`, `last_channel`, `last_received`, `last_sender_hops`, `last_sender_hops_available`, `neighbor_long_name`, `neighbor_short_name`, `neighbor_snr`, and `neighbor_hops_away`. Values are private HA entity IDs and stay only in `.env`. The public response returns the local configured node name and at most one explicitly approved neighbor's configured name, SNR, and hops-away value; it does not enumerate nodes or expose IDs, positions, routes, or raw attributes. Set `SIGNAL_RELAY_MESHTASTIC_TURNSTILE_SECRET` to enable the public broadcast endpoint. Create a managed Cloudflare Turnstile widget for `info.destaben.dev`, add its site key to the GitHub Actions variable `TURNSTILE_SITE_KEY`, and enter its secret only in the deployment `.env`. The relay validates the Turnstile response, applies a cooldown, and calls only `script.meshtastic_public_broadcast`; it cannot select a different channel or any other HA service.

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
sudo docker network create destaben-edge
sudo docker compose config
sudo docker compose pull
sudo docker compose up -d
```

The relay has no host port and joins the external `destaben-edge` network. Deploy and operate Nginx and Cloudflare Tunnel from [`destaben/lab-inverse-proxy`](https://github.com/destaben/lab-inverse-proxy); start the edge after the relay has joined the shared network. The edge places Cloudflared on an isolated internal ingress network and does not attach it to `destaben-edge`. Before deploying the edge, check that its reserved `172.30.250.0/29` subnet does not overlap Docker, LAN, or VPN networks. Do not replace `.env`, `reticulum/`, `lab-sender-reticulum/`, or the `signal-relay-data` volume during updates: they hold secrets and persistent identities.

When public bootstrap transports change, manually merge their interface entries from `reticulum-config.example` into the private `reticulum/config`. Do not replace the Reticulum directory wholesale. If the relay cannot parse its configuration, inspect `reticulum/config`, ensure it has `[reticulum]` and `[interfaces]` root sections, then run `sudo docker compose config` and recreate only `signal-relay`.

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
