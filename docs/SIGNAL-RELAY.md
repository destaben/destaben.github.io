# Reticulum Contact Contract

Reticulum Contact is a separate, self-hosted service. It is not hosted by GitHub Pages and is intentionally absent from this repository's runtime. Learn more at [reticulum.network](https://reticulum.network).

## Boundary

```text
Browser -> HTTPS/WSS -> lab.destaben.dev -> cloudflared -> nginx -> bridge -> Reticulum
```

The browser obtains the public Reticulum destination hash only from `GET /v1/contact`. Educational session responses, inbox notices, events, and node projections never provide a destination address or hash. The browser never receives a Reticulum private identity, private key, daemon port, home IP address, or direct access to the node. The bridge is the only component that speaks both web protocols and Reticulum.

## Public API

`GET /healthz` returns an aggregate health object. It must not include interface names, peer identities, path tables, or host metrics.

```json
{
  "status": "ready",
  "lastHeartbeat": "2026-09-19T08:00:00Z",
  "transport": "reticulum"
}
```

`GET /v1/contact` returns the public Reticulum delivery destination after the node is configured.

```json
{
  "scheme": "lxmf.delivery",
  "address": "<public-destination-hash>"
}
```

`GET /v1/inbox` returns the newest 20 received messages. Each entry contains an opaque ID, receipt timestamp, and a normalized plain-text body capped at 1,000 characters. It never exposes titles, source hashes, sender identities, or network metadata.

`GET /v1/lab/capabilities` returns only whether educational sending is currently enabled and whether Telegram notifications are configured. It never reveals notification credentials or destinations.

`GET /v1/lab/reticulum-nodes` returns a fixed public projection of public names for configured Reticulum TCP connections and their current connection states:

```json
{
  "status": "available",
  "nodes": [
    {"alias": "Node One", "status": "up"}
  ]
}
```

It returns `{"status":"unavailable","nodes":[]}` when Reticulum is not active or no aliases are configured. The projection contains only configured public aliases and `up` or `down` statuses, with at most 12 aliases. Public aliases must be unique, begin with an ASCII letter or digit, and contain only ASCII letters, digits, spaces, periods, underscores, or hyphens, with a maximum of 48 characters. They are public names for configured TCP connections, not names or bindings for the LXMF destination. `up` means the bridge currently observes the corresponding `TCPClientInterface.online` state; it is not a route, path, or delivery guarantee. Configure the private JSON mapping in `SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES`, where private TCP client interface names map to unique public aliases. Never return, log, or publish that mapping, interface names, addresses, or other topology. Logs record each alias's initial observed connection status, later status changes, and observation failures. They contain only the public alias and status where applicable.

## Educational Reticulum sessions

The portfolio may create a short-lived, browser-scoped educational session only when `SIGNAL_RELAY_LAB_SEND_ENABLED=true` and `SIGNAL_RELAY_LAB_SENDER_CONFIG_DIR` identifies a separate, reachable Reticulum client configuration. On send, the bridge starts an isolated official Reticulum runtime with a new temporary identity, sends once through the configured transport, and removes its temporary storage on exit. Public session responses contain an opaque session ID plus only the bounded `state`, `errorCode`, `expiresInSeconds`, and observed public `nodeAlias` fields. They omit both source and destination hashes; temporary source hashes and delivery correlation remain internal to the relay. The separate runtime is required because one Reticulum runtime cannot route to its own delivery destination.

The endpoints are disabled by default and must remain disabled until both Reticulum configurations have a verified external route. When enabled, a session expires after 15 minutes and may emit one Reticulum message at most. The Nginx edge limits laboratory POSTs to five requests per Cloudflare client IP per minute, while status polling remains unrestricted. The browser reports only the actual `identity_ready`, `queued`, `delivered`, or `failed` state from the official Reticulum runtime; it does not simulate delivery. A `failed` session includes a bounded public `errorCode`, currently `lab_sender_unconfigured`, `path_unavailable`, `destination_unavailable`, `delivery_failed`, `delivery_timeout`, or `outbound_error`.

An educational session may include `nodeAlias` only after its isolated sender selects an actual Reticulum route whose TCP client interface has a configured public alias. This is the only route-specific alias exposed by the service; it records that observed outbound lab-send selection and does not bind the LXMF address to that connection. The field is otherwise empty and never reveals a private interface name, route, path, address, or topology.

`GET /metrics` exposes Prometheus-format operational counters. It is intended for the operator's scraper, not for the portfolio interface.

`GET /v1/lab/metrics` is the portfolio observability route. It accepts only `cpu` or `memory` and a bounded time range, then queries a configured internal Prometheus endpoint with fixed cAdvisor queries. It returns only container display names and timestamped aggregate values. It does not accept PromQL, scrape targets, arbitrary labels, host metrics, or Prometheus credentials.

`GET /v1/lab/home-status` is the Home Assistant laboratory route. It takes no parameters and returns either `503 home_status_unavailable` or a fixed public projection:

```json
{
  "status": "available",
  "temperatureC": 22,
  "humidityPercent": 45,
  "airQuality": "good",
  "refreshedAt": "2026-09-19T08:15:00Z"
}
```

The relay uses a dedicated long-lived Home Assistant token plus explicitly configured temperature, humidity, and air-quality entities. These values are private deployment configuration and must never appear in Git, browser code, logs, or API responses. The air-quality value is classified privately as `good`, `regular`, or `bad`; its raw value is never public. Values remain cached for at least 15 minutes. The public route never exposes entity IDs, friendly names, attributes, room names, individual state timestamps, history, versions, errors, or Home Assistant controls.

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

Run Reticulum, the bridge, Nginx, and the tunnel under separate unprivileged containers. The Compose deployment runs `cloudflare/cloudflared` as a separate sidecar and reads `CLOUDFLARE_TUNNEL_TOKEN` only from the ignored `.env` file. It also passes `SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES` from that private file, defaulting to an empty mapping. Create the remotely managed tunnel in Cloudflare Zero Trust and map `lab.destaben.dev` to `http://nginx:8080`. Nginx remains the sole public HTTP policy point: it allowlists portfolio API routes, including `GET /v1/lab/reticulum-nodes`, limits laboratory POSTs and trusts the Cloudflare client-IP header only because it has no public host binding. Its internal `8081` listener has no host port or Cloudflare ingress and proxies the relay's fixed Home Assistant reads to `host.docker.internal:8123`; it is not a Home Assistant public proxy.

The deployment supports CGNAT through outbound Reticulum `TCPClientInterface` transports and the outbound Cloudflare HTTP tunnel. Cloudflare Tunnel cannot expose arbitrary Reticulum TCP clients; a standard public `TCPServerInterface` would require a reachable public port or a separately operated TCP relay on a VPS. Do not publish the relay HTTP API, Reticulum TCP, Home Assistant, or any other host port. Keep secrets, Home Assistant credentials and entity IDs, Telegram credentials, and Reticulum identities outside Git and rotate tunnel credentials.

An optional `AutoInterface` supports local discovery only. For off-LAN LXMF delivery, configure a trusted Reticulum transport interface that both peers can reach. `services/signal-relay/reticulum-config.example` provides the current public bootstrap transports as the deployment starter. Existing deployments must merge refreshed bootstrap entries into their private `reticulum/config`; they must not replace the Reticulum directory or remove deployment-specific interfaces. When recovering from a broken configuration, the exact procedure in `services/signal-relay/README.md` may replace only `reticulum/config` with the current template, refresh the companion Compose and Nginx files, and recreate the relay and Nginx. It must preserve `.env`, `lab-sender-reticulum/`, and the `signal-relay-data` volume; reapply any intentional private interface additions afterward. The private node-alias mapping must match the configured interface names before it can report connection transitions. Announcing a destination alone does not create an Internet route.

The supported container image is `ghcr.io/destaben/signal-relay:latest`. It is published for `linux/amd64` and `linux/arm64` by `.github/workflows/publish-signal-relay.yml`. The companion Compose file keeps the relay off the host network, binds the Nginx diagnostics entry point to loopback, persists Reticulum configuration and service state, and drops Linux capabilities. Future services can join the `destaben-edge` Docker network, then be routed explicitly by Nginx. See `services/signal-relay/README.md` for the exact host setup and update commands.

## Acceptance checks

1. Restarting the bridge retains the same LXMF destination identity.
2. An incoming LXMF message produces one retained plain-text inbox entry without exposing sender metadata.
3. Rate-limited web signals produce a public rejection code but do not reveal policy internals.
4. The public endpoint exposes no private network, Reticulum, scrape-target, or monitoring configuration details. The laboratory metrics route exposes only its documented aggregate container series.
5. Prometheus captures inbound message counts and the retained inbox size.
6. With Telegram credentials configured, an incoming message produces one private notification; a Telegram failure does not interrupt inbox persistence or LXMF delivery.
7. The Home Assistant laboratory route returns only its documented delayed temperature, humidity, status, and aggregate refresh time; Home Assistant has no public route through `lab.destaben.dev`.