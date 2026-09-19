# Reticulum Contact

Self-hosted service for the public Reticulum contact point. It is intentionally separate from the Astro site: GitHub Pages cannot run persistent APIs or WebSockets. See the [official Reticulum website](https://reticulum.network) for the network and protocol.

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

Set `SIGNAL_RELAY_MODE=reticulum` and optionally `SIGNAL_RELAY_RETICULUM_CONFIG_DIR` to initialise the official `rns` runtime. The service persists a private delivery identity under `SIGNAL_RELAY_STORAGE_DIR`, announces its LXMF destination hash, and retains the newest 20 message bodies as bounded plain text. Keep the storage directory and service configuration outside Git.

The default Reticulum configuration only enables link-local discovery. To accept messages from a device outside the local network, configure a Reticulum interface that both devices can reach, such as a trusted `TCPClientInterface` transport. Do not expose the service HTTP port or Reticulum's TCP interface directly to the Internet.

## Telegram notifications

Telegram notifications are optional. Create a bot with BotFather, start a private chat with it, and configure both variables in the service environment:

```sh
export SIGNAL_RELAY_TELEGRAM_BOT_TOKEN='replace-with-the-bot-token'
export SIGNAL_RELAY_TELEGRAM_CHAT_ID='replace-with-your-private-chat-id'
```

Every received LXMF message is then forwarded to that chat after it is stored locally. Notifications run in the background and failures do not interrupt LXMF delivery. The token and chat ID are secrets: do not commit them, put them in the public website, or add them to `.env.example`.

## Educational Reticulum session

The portfolio includes an optional Reticulum walkthrough. It needs both `SIGNAL_RELAY_LAB_SEND_ENABLED=true` and `SIGNAL_RELAY_LAB_SENDER_CONFIG_DIR` pointing to a second, reachable Reticulum client configuration. Each send starts an isolated official Reticulum runtime with a new temporary identity, sends one short Reticulum message to the configured destination, then removes its temporary storage. The second runtime is necessary: a Reticulum runtime cannot establish a route to its own delivery destination.

This is disabled by default. Enable it only after configuring both Reticulum clients to reach the same trusted transport. The sender configuration must be separate from the relay configuration. Nginx limits public session creation and sends to five requests per Cloudflare client IP per minute; the limit lives in `nginx/nginx.conf` with the rest of the public edge policy. Session identities, private keys, message text, and session capabilities are never persisted, forwarded to Telegram, returned through the public inbox, or exported as metrics. A session reports `identity_ready`, `queued`, `delivered`, or `failed`; failures include a bounded public `errorCode` such as `path_unavailable`, `delivery_failed`, or `delivery_timeout`.

## Container deployment

GitHub Actions publishes a multi-architecture image to GitHub Container Registry on every `main` push that changes this service:

```text
ghcr.io/destaben/signal-relay:latest
```

Make the package public in GitHub Packages before a host pulls it anonymously. On the deployment host, copy `compose.yaml` and `.env.example` into a private directory, then configure the environment file and Reticulum directory:

```sh
mkdir -p /opt/signal-relay/nginx /opt/signal-relay/reticulum /opt/signal-relay/lab-sender-reticulum
cd /opt/signal-relay
curl -fsSLo compose.yaml https://raw.githubusercontent.com/destaben/destaben.github.io/main/services/signal-relay/compose.yaml
curl -fsSLo nginx/nginx.conf https://raw.githubusercontent.com/destaben/destaben.github.io/main/services/signal-relay/nginx/nginx.conf
curl -fsSLo .env https://raw.githubusercontent.com/destaben/destaben.github.io/main/services/signal-relay/.env.example
chmod 600 .env
sudo chown 10001:10001 reticulum lab-sender-reticulum
```

Set `SIGNAL_RELAY_TELEGRAM_BOT_TOKEN` and `SIGNAL_RELAY_TELEGRAM_CHAT_ID` in `.env` when Telegram notifications are required. In Cloudflare Zero Trust, create a remotely managed tunnel and assign `lab.destaben.dev` to `http://nginx:8080`. Copy its token into `.env` as `CLOUDFLARE_TUNNEL_TOKEN`; do not quote it in shell output or commit it. Start and update the service with:

```sh
docker compose pull
docker compose up -d
docker compose ps
```

To update an existing deployment, download only `compose.yaml` and `nginx/nginx.conf` from the same URLs, then run `docker compose up -d --remove-orphans`. Do not replace `.env`, `reticulum/`, or `lab-sender-reticulum/`: they contain local secrets and persistent identities.

To diagnose the latest browser laboratory send without copying a session ID, download and run the diagnostic after the test:

```sh
curl -fsSLo diagnose-last-lab-session.sh https://raw.githubusercontent.com/destaben/destaben.github.io/main/services/signal-relay/diagnose-last-lab-session.sh
sudo sh diagnose-last-lab-session.sh
```

The relay has no host port. Nginx is the only HTTP entry point and binds to `127.0.0.1:8080` for host diagnostics; it exposes only the portfolio routes, limits laboratory POSTs, and rejects all other paths. Its `destaben-edge` Docker network can be joined by future services, then routed explicitly in `nginx/nginx.conf`. The `cloudflared` sidecar creates the outbound HTTPS tunnel when `CLOUDFLARE_TUNNEL_TOKEN` is set. The `reticulum/` directory contains the persistent Reticulum configuration; the named volume retains the LXMF identity and inbox across image upgrades.

## Home Assistant environment lab

The optional Home Assistant panel is a read-only public projection. It shows only rounded indoor temperature and humidity plus an air-quality category, cached for at least 15 minutes. It is not a Home Assistant dashboard or remote control.

Create a dedicated Home Assistant user/token with the minimum read access required, then set these values in the private deployment `.env`:

```sh
SIGNAL_RELAY_HOME_ASSISTANT_TOKEN='replace-with-dedicated-token'
SIGNAL_RELAY_HOME_ASSISTANT_TEMPERATURE_ENTITY_ID='replace-with-temperature-entity'
SIGNAL_RELAY_HOME_ASSISTANT_HUMIDITY_ENTITY_ID='replace-with-humidity-entity'
SIGNAL_RELAY_HOME_ASSISTANT_AIR_QUALITY_ENTITY_ID='replace-with-pm25-or-co2-entity'
SIGNAL_RELAY_HOME_ASSISTANT_CACHE_SECONDS=900
```

Do not commit these values or use the administrator token. The relay speaks to Nginx's internal-only `8081` listener; Nginx reaches Home Assistant at `host.docker.internal:8123`. No new host port or Cloudflare route is created for Home Assistant. This configuration deliberately excludes presence, cameras, alarms, locks, doors, windows, lights, switches, automations, media, energy, room names, device names, attributes, and history. Keep Home Assistant remote access on the private VPN, and do not add a WAN port-forward for `8123`.

Keep the optional `lab-sender-reticulum/` configuration separate and give it an interface that reaches the relay's configured transport. Leave `SIGNAL_RELAY_LAB_SEND_ENABLED=false` until that route and the public anti-bot control are verified.

## Tests

```sh
.venv/bin/python -m pytest
```

## End-to-end verification

Run the portfolio and bridge in separate terminals:

```sh
# Repository root
npm run dev -- --host 127.0.0.1 --port 4321

# services/signal-relay
SIGNAL_RELAY_MODE=reticulum .venv/bin/uvicorn signal_relay.app:app --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:4321`. The Reticulum contact panel fetches `http://127.0.0.1:8787/v1/contact` and `/v1/inbox` on local hosts. In Reticulum mode it displays the persistent LXMF destination hash.

To preview an arrival notice without sending a real LXMF message, start the bridge in `demo` mode and run:

```sh
curl -X POST http://127.0.0.1:8787/v1/demo/inbox \
	-H 'content-type: application/json' \
	-d '{"content":"Hola desde una prueba local"}'
```

Refresh the portfolio page: the message and timestamp appear in the inbox. This endpoint exists only in `demo` mode and returns `404` in Reticulum mode.

Verify the API does not leak network details:

```sh
curl -H 'Origin: http://127.0.0.1:4321' http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/v1/contact
```

For a complete accepted-and-acknowledged signal loop, use a second local service in clearly labelled demo mode:

```sh
SIGNAL_RELAY_MODE=demo .venv/bin/uvicorn signal_relay.app:app --host 127.0.0.1 --port 8788
curl -X POST http://127.0.0.1:8788/v1/signals -H 'content-type: application/json' -d '{"action":"ping"}'
```

The Reticulum-mode bridge deliberately rejects public web signals with `503 transport_not_configured`. Direct LXMF contact does not use this HTTP endpoint; the service receives LXMF through its published delivery destination.