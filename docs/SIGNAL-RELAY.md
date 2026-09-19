# Signal Relay Contract

Signal Relay is a separate, self-hosted service. It is not hosted by GitHub Pages and is intentionally absent from this repository's runtime.

## Boundary

```text
Browser -> HTTPS/WSS -> lab.info.destaben.dev -> bridge -> Reticulum / LXMF
```

The browser receives only the public LXMF destination hash. It never receives a Reticulum private identity, private key, daemon port, home IP address, or direct access to the node. The bridge is the only component that speaks both web protocols and Reticulum.

## Public API

`GET /healthz` returns an aggregate health object. It must not include interface names, peer identities, path tables, or host metrics.

```json
{
  "status": "ready",
  "lastHeartbeat": "2026-09-19T08:00:00Z",
  "transport": "reticulum"
}
```

`GET /v1/contact` returns the public LXMF delivery destination after the Reticulum node is configured.

```json
{
  "scheme": "lxmf.delivery",
  "address": "<public-destination-hash>"
}
```

`GET /v1/inbox` returns the newest 20 received messages. Each entry contains an opaque ID, receipt timestamp, and a normalized plain-text body capped at 1,000 characters. It never exposes titles, source hashes, sender identities, or network metadata.

`GET /v1/lab/capabilities` returns only whether educational sending is currently enabled and whether Telegram notifications are configured. It never reveals notification credentials or destinations.

## Educational LXMF sessions

The portfolio may create a short-lived, browser-scoped educational session only when `SIGNAL_RELAY_LAB_SEND_ENABLED=true` and `SIGNAL_RELAY_LAB_SENDER_CONFIG_DIR` identifies a separate, reachable Reticulum client configuration. On send, the bridge starts an isolated official RNS/LXMF runtime with a new temporary identity. It returns the public source hash only to that browser session, sends once through the configured transport, and removes its temporary LXMF storage on exit. The separate runtime is required because one Reticulum runtime cannot route to its own delivery destination.

The endpoints are disabled by default and must remain disabled until both Reticulum configurations have a verified external route and an anti-bot control is in place. When enabled, a session expires after 15 minutes and may emit one LXMF message at most. The browser reports only the actual `identity_ready`, `queued`, `delivered`, or `failed` state from the official LXMF runtime; it does not simulate delivery. A `failed` session includes a bounded `errorCode`, currently `lab_sender_unconfigured`, `path_unavailable`, `destination_unavailable`, `delivery_failed`, `delivery_timeout`, or `outbound_error`.

`GET /metrics` exposes Prometheus-format operational counters. It is intended for the operator's scraper, not for the portfolio interface.

`WSS /v1/events` emits only these server events:

- `relay.status`: `connecting`, `ready`, `maintenance`, or `unavailable`
- `relay.heartbeat`: aggregate timestamp and state
- `signal.accepted`: anonymous event ID
- `signal.acknowledged`: anonymous event ID and acknowledgement latency
- `signal.rejected`: anonymous event ID and public rejection code

No event includes message content, source address, IP address, Reticulum destination hash, or a cryptographic identity.

## Telegram notifications

When both `SIGNAL_RELAY_TELEGRAM_BOT_TOKEN` and `SIGNAL_RELAY_TELEGRAM_CHAT_ID` are configured, the bridge forwards each received LXMF message body to that private Telegram chat. The credentials are required together, remain outside this repository, and are never returned by an API or included in metrics.

Telegram notification work runs after local inbox persistence and does not block or fail LXMF delivery. Metrics record successful and failed notification attempts without identifying the chat or exposing message text.

## Public input

Public input remains disabled until the service has all of the following:

- Strict JSON schema and maximum payload length
- Per-session and per-IP rate limits
- Origin allowlist for `https://info.destaben.dev`
- Bot challenge before opening a send action
- Short retention period for audit events
- Moderation and deletion procedure
- Metrics, alerts, and a documented kill switch

When enabled, `POST /v1/signals` accepts only a fixed action vocabulary. It does not accept arbitrary chat messages.

## Deployment

Run Reticulum, the bridge, and the tunnel under separate unprivileged service accounts or containers. Use an outbound HTTPS tunnel; do not forward residential ports and do not expose Reticulum's TCP interface. Keep secrets, Telegram credentials, and Reticulum identities outside Git and rotate tunnel credentials.

The default `AutoInterface` supports local discovery only. For off-LAN LXMF delivery, configure a trusted Reticulum transport interface that both peers can reach. Announcing a destination alone does not create an Internet route.

The supported container image is `ghcr.io/destaben/signal-relay:latest`. It is published for `linux/amd64` and `linux/arm64` by `.github/workflows/publish-signal-relay.yml`. The companion Compose file binds the HTTP API to loopback, runs as an unprivileged user, persists Reticulum configuration and service state, and drops Linux capabilities. See `services/signal-relay/README.md` for the exact host setup and update commands.

## Acceptance checks

1. Restarting the bridge retains the same LXMF destination identity.
2. An incoming LXMF message produces one retained plain-text inbox entry without exposing sender metadata.
3. Rate-limited web signals produce a public rejection code but do not reveal policy internals.
4. The public endpoint exposes no private network, Reticulum, or monitoring details.
5. Prometheus captures inbound message counts and the retained inbox size.
6. With Telegram credentials configured, an incoming message produces one private notification; a Telegram failure does not interrupt inbox persistence or LXMF delivery.