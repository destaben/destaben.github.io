# Signal Relay

Self-hosted service for the public Reticulum contact point. It is intentionally separate from the Astro site: GitHub Pages cannot run persistent APIs or WebSockets.

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

## Educational browser session

The portfolio includes an optional LXMF walkthrough. It needs both `SIGNAL_RELAY_LAB_SEND_ENABLED=true` and `SIGNAL_RELAY_LAB_SENDER_CONFIG_DIR` pointing to a second, reachable Reticulum client configuration. Each send starts an isolated official RNS/LXMF runtime with a new temporary identity, sends one short LXMF message to the configured Signal Relay destination, then removes its temporary LXMF storage. The second runtime is necessary: a Reticulum runtime cannot establish a route to its own delivery destination.

This is disabled by default. Enable it only after configuring both Reticulum clients to reach the same trusted transport and adding an anti-bot control at the public proxy. The sender configuration must be separate from the relay configuration. Session identities, private keys, message text, and session capabilities are never persisted, forwarded to Telegram, returned through the public inbox, or exported as metrics. A session reports `identity_ready`, `queued`, `delivered`, or `failed`; failures include a bounded public `errorCode` such as `path_unavailable`, `delivery_failed`, or `delivery_timeout`.

## Container deployment

GitHub Actions publishes a multi-architecture image to GitHub Container Registry on every `main` push that changes this service:

```text
ghcr.io/destaben/signal-relay:latest
```

Make the package public in GitHub Packages before a host pulls it anonymously. On the deployment host, copy `compose.yaml` and `.env.example` into a private directory, then configure the environment file and Reticulum directory:

```sh
mkdir -p /opt/signal-relay/reticulum /opt/signal-relay/lab-sender-reticulum
cd /opt/signal-relay
curl -O https://raw.githubusercontent.com/destaben/personalwebsite/main/services/signal-relay/compose.yaml
curl -o .env https://raw.githubusercontent.com/destaben/personalwebsite/main/services/signal-relay/.env.example
chmod 600 .env
sudo chown 10001:10001 reticulum lab-sender-reticulum
```

Set `SIGNAL_RELAY_TELEGRAM_BOT_TOKEN` and `SIGNAL_RELAY_TELEGRAM_CHAT_ID` in `.env` when Telegram notifications are required. Start and update the service with:

```sh
docker compose pull
docker compose up -d
docker compose ps
```

The Compose file binds the HTTP API to `127.0.0.1:8787` only. Put a reverse proxy or outbound HTTPS tunnel in front of it if the portfolio needs browser access. The `reticulum/` directory contains the persistent Reticulum configuration; the named volume retains the LXMF identity and inbox across image upgrades.

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
curl -H 'Origin: http://127.0.0.1:4321' http://127.0.0.1:8787/healthz
curl http://127.0.0.1:8787/v1/contact
curl http://127.0.0.1:8787/metrics
```

For a complete accepted-and-acknowledged signal loop, use a second local service in clearly labelled demo mode:

```sh
SIGNAL_RELAY_MODE=demo .venv/bin/uvicorn signal_relay.app:app --host 127.0.0.1 --port 8788
curl -X POST http://127.0.0.1:8788/v1/signals -H 'content-type: application/json' -d '{"action":"ping"}'
```

The Reticulum-mode bridge deliberately rejects public web signals with `503 transport_not_configured`. Direct LXMF contact does not use this HTTP endpoint; the service receives LXMF through its published delivery destination.