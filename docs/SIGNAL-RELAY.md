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
    {"alias": "Node One", "url": "tcp://node-one.example:4242", "status": "up"}
  ]
}
```

It returns `{"status":"unavailable","nodes":[]}` when Reticulum is not active or either public node mapping is missing or inconsistent. The projection contains only configured public aliases, intentionally public `tcp://host:port` URLs and `up` or `down` statuses, with at most 12 aliases. Public aliases must be unique, begin with an ASCII letter or digit, and contain only ASCII letters, digits, spaces, periods, underscores, or hyphens, with a maximum of 48 characters. Each URL must use `tcp`, have a host and explicit port, and omit credentials, paths, queries, fragments, stray `?` or `#` even when empty, non-ASCII, invisible, whitespace or control characters, or percent-escapes (the URL must be printable ASCII), non-global literal IP addresses, IPv4-embedding IPv6 addresses (NAT64 `64:ff9b::/96` and `64:ff9b:1::/48`, IPv4-compatible `::/96`, 6to4 `2002::/16`, and Teredo `2001::/32`), IPv6 that is not bracketed (bare IPv6 and bracketed IPv4 are rejected), non-canonical IPv4 spellings such as `127.1` or `0x7f.1`, single-label hostnames or private-use hostname suffixes such as `.lan`, `.local`, `.internal`, `.home.arpa`, `.box` (which covers `.fritz.box`), `.router`, `.gateway`, `.modem`, `.wan`, `.domain` and `.mshome.net`, and empty labels including a trailing dot. They are public names and published endpoints for configured TCP connections, not names or bindings for the LXMF destination. `up` means the bridge currently observes the corresponding `TCPClientInterface.online` state; it is not a route, path, or delivery guarantee. Configure the private JSON mapping in `SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES`, where private TCP client interface names map to unique public aliases, and the private `SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS` JSON mapping from each alias to its intentionally public URL. Both mappings must define exactly the same aliases. Never return or log interface names, addresses other than the intentionally public URLs, or other topology. Logs record each alias's initial observed connection status, later status changes, and observation failures. They contain only the public alias and status where applicable.

## Educational Reticulum sessions

The portfolio may create a short-lived, browser-scoped educational session only when `SIGNAL_RELAY_LAB_SEND_ENABLED=true` and `SIGNAL_RELAY_LAB_SENDER_CONFIG_DIR` identifies a separate, reachable Reticulum client configuration. On send, the bridge starts an isolated official Reticulum runtime with a new temporary identity, sends once through the configured transport, and removes its temporary storage on exit. Public session responses contain an opaque session ID plus only the bounded `state`, `errorCode`, `expiresInSeconds`, and observed public `nodeAlias` fields. They omit both source and destination hashes; temporary source hashes and delivery correlation remain internal to the relay. The separate runtime is required because one Reticulum runtime cannot route to its own delivery destination.

The endpoints are disabled by default and must remain disabled until both Reticulum configurations have a verified external route. When enabled, a session expires after 15 minutes and may emit one Reticulum message at most. The Nginx edge limits every public request to 120 requests per Cloudflare client IP per minute and limits laboratory POSTs to five requests per Cloudflare client IP per minute. It may return `429` for bursts; the browser treats that as a transient unavailable state. The browser reports only the actual `identity_ready`, `queued`, `delivered`, or `failed` state from the official Reticulum runtime; it does not simulate delivery. A `failed` session includes a bounded public `errorCode`, currently `lab_sender_unconfigured`, `path_unavailable`, `destination_unavailable`, `delivery_failed`, `delivery_timeout`, or `outbound_error`.

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

The relay uses a dedicated long-lived Home Assistant token plus explicitly configured temperature, humidity, and air-quality entities. These values are private deployment configuration and must never appear in Git, browser code, logs, or API responses. The air-quality value is classified privately as `good`, `regular`, or `bad`; its raw value is never public. Values remain cached for at least 15 minutes, and a failed refresh is remembered for 30 seconds. No new Home Assistant read starts once a refresh is 10 seconds old. Each request has a 5-second budget that starts when the request does and is checked after each response chunk, so a slow or trickling body is cut off at the next chunk after the budget is spent; response bodies are also refused above 1 MiB. Each socket operation waits at most 5 seconds, so a header stream that trickles in is limited only by that per-operation timeout. A read therefore ends within about 10 seconds of starting, unless its headers trickle, and a refresh within about 20 seconds; concurrent callers wait on that single refresh, and fresh cache hits never wait on a refresh, and redirects are never followed, so the Bearer token is never sent to another location. The public route never exposes entity IDs, friendly names, attributes, room names, individual state timestamps, history, versions, errors, or Home Assistant controls.

`GET /v1/lab/meshtastic-status` is the Meshtastic laboratory route. It takes no parameters and returns either `503 meshtastic_status_unavailable` or a fixed, delayed public projection:

```json
{
  "status": "available",
  "onlineNodes": 12,
  "totalNodes": 43,
  "channels": [
    {
      "name": "Longfast",
      "last": {
        "nodeId": "!7e5d1a**",
        "text": "<sanitized public message>",
        "time": "2026-09-25T08:14:00Z",
        "hops": 2
      }
    }
  ],
  "refreshedAt": "2026-09-25T08:15:00Z"
}
```

The relay uses the existing dedicated Home Assistant token and the private `SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS` map shared with the Meshtastic send projection, reading only its `gateway`, `nodes_online`, and `nodes_total` entities for the counts and gateway state. Channel discovery is separate: only when the allowlist is set does the relay also read the entity list from `GET /api/states`. The gateway state must be `Connected`, matching that projection. Malformed Meshtastic or Home Assistant entity IDs, and invalid channel allowlist, denylist, prefix, or field settings, stop the relay at startup with an error that names the setting and never echoes the value. Successful values are cached for at least 15 minutes (`SIGNAL_RELAY_MESHTASTIC_STATUS_CACHE_SECONDS`, default and minimum 900), and a failed refresh is remembered for 30 seconds before Home Assistant is queried again. Publication is default-deny. Only channels whose sanitized name appears in the private `SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST` can be published, and an empty allowlist omits `channels` entirely without reading the entity list. When the allowlist is set, channels are discovered from one `GET /api/states` read per refresh. An entity is a candidate only when its ID starts with the private `SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX` (default: the gateway entity ID followed by `_channel_`), passes the entity-ID check, and is allowlisted by name. `SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST` wins over the allowlist and hides channels by name or slug. `SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS` maps `text`, `node_id`, `timestamp`, `hop_start`, and `hop_limit` to the attribute names carried on the host; a field without a configured name is never read. Direct-message detection is a heuristic, not the safeguard: a candidate whose checked words (see below) contain a word token from the direct-message list (`dm`, `dms`, `pm`, `pms`, `direct`, `directa`, `directas`, `directo`, `directos`, `private`, `privada`, `privadas`, `privado`, `privados`, `whisper`, `secret`) is excluded, and so is one whose attributes cannot be read. The check covers the entity ID suffix, the channel friendly name with the gateway's own friendly name removed, and any words of a custom channel prefix that the gateway's entity ID and friendly name do not already contain. A direct message without such a token is published only if its name is allowlisted, so the allowlist and denylist must be reviewed before the projection is enabled. At most 16 channels are published, in entity-ID order. Each carries its name and only its last public message. The sender node ID keeps its first six hexadecimal digits and replaces its last two characters with `**`; the text is sanitized and capped at 200 characters; the time is UTC; hops appear only when hop start and limit are consistent. Node IDs written inside the message text are masked the same way. A channel without a usable message is listed without one, and a failed channel read omits `channels` without failing the counts. The counts stay cached for their normal window, but a status whose channel list could not be read is kept for only 60 seconds, so channel discovery is retried soon after. The entity list read shares the 1 MiB Home Assistant response cap, so on a very large installation the list may be too large and channels are omitted. The public route never exposes Home Assistant entity IDs, gateway names, full node identifiers, locations, telemetry, direct messages, attributes, or controls, and the message time is the only timestamp it publishes. Counts are whole numbers from 0 to 100000, the same limit in the relay and in the browser; a larger count is invalid and returns `503 meshtastic_status_unavailable`. Gateway states other than `Connected`, invalid counts, other HTTP errors (such as 401 or 500) on the gateway or count reads, and transport errors on those reads still make the route return `503 meshtastic_status_unavailable`. This status route is read-only; public sending is the separate `POST` route documented below.

`GET /v1/lab/meshtastic` returns a bounded public Meshtastic projection or `503 meshtastic_unavailable`. It includes the configured local node's public name, gateway availability and power state, aggregate node and packet counters, channel utilization, airtime, per-minute traffic/error rates, and at most five explicitly sanitized MediumFast public-channel records, newest first. Each record includes the sender's public node name. The relay reads only the five fixed Home Assistant helpers configured for this public queue; malformed or incomplete entries are omitted. It never enumerates the mesh or exposes Home Assistant entity IDs, attributes, device configuration, channel keys, node IDs, positions, SNR, RSSI, routes, other channels, unbounded message history, or Home Assistant errors.

`POST /v1/lab/meshtastic/messages` accepts only `{"message":"...","turnstileToken":"..."}` and returns `202 {"status":"accepted"}` only after Home Assistant accepts the fixed `meshtastic_public_broadcast` event. A Home Assistant automation maps that event only to `script.meshtastic_public_broadcast`. The message must be one trimmed, printable UTF-8 line of at most 237 bytes. The route rejects missing/invalid Turnstile responses, unavailable configuration, invalid payloads, and per-client/global cooldowns. It never accepts a channel, recipient, radio setting, node identifier, or arbitrary Home Assistant service. Accepted means Home Assistant accepted the event; it is not an RF delivery acknowledgement.

The static portfolio loads Turnstile only when the public build variable `PUBLIC_TURNSTILE_SITE_KEY` is present. GitHub Pages builds read it from the repository Actions variable `TURNSTILE_SITE_KEY`, falling back to a secret of the same name; pull-request CI builds read only the variable. The value is public by design. Create a managed Turnstile widget for `info.destaben.dev` before setting that variable, then set the widget secret only as `SIGNAL_RELAY_MESHTASTIC_TURNSTILE_SECRET` in the private Signal Relay deployment `.env`. Never commit the secret or expose it to the browser.

## 3D printer laboratory

The printer laboratory shows the job that a Klipper/Moonraker printer is running. It is disabled by default. While `SIGNAL_RELAY_PRINTER_ENABLED` is not `true`, all three routes below return `404`, the same as an unknown path. Enabling it requires `SIGNAL_RELAY_PRINTER_BASE_URL`; the relay refuses to start when the lab is enabled without it. The value must be a plain `http` origin with no path, query, fragment, or credentials, and a malformed value stops startup even while the lab is disabled. The Compose file and `.env.example` set it to `http://nginx:8082`, the edge's internal `8082` listener in [`destaben/lab-inverse-proxy`](https://github.com/destaben/lab-inverse-proxy). That listener proxies only the four fixed Moonraker requests listed below. The relay never contacts Moonraker or the printer host directly, and it publishes no host port.

Rollout order: (1) deploy the edge's `8082` listener and the public allowlist entries in `destaben/lab-inverse-proxy`; (2) publish the relay image from `main`; (3) deploy the relay with the lab disabled; (4) only while the printer is idle, set `SIGNAL_RELAY_PRINTER_ENABLED=true` and `SIGNAL_RELAY_PRINTER_BASE_URL` in the host's private `.env` and recreate `signal-relay`. Do not enable the lab before step 1 is live.

`GET /v1/lab/printer` returns the current state. It is served with `Cache-Control: no-store`.

```json
{
  "state": "printing",
  "progress": 0.42,
  "layer": {"current": 12, "total": 85},
  "heightMm": 2.4,
  "objectHeightMm": 40.0,
  "modelId": "0123456789abcdef0123456789abcdef",
  "thumbnail": true,
  "updatedAt": "2026-11-04T09:00:00Z"
}
```

`state` is `idle` (Moonraker standby), `printing`, `paused`, `complete`, `cancelled`, `error` (the print failed), or `unavailable`. `unavailable` covers an unreachable printer, a Moonraker error, a malformed or oversized response, and an unknown state. It is returned with `200`, never `5xx`, so the site can show its fallback animation. `progress` is a number from 0 to 1, or `null`. `layer.current` is the number of layer changes at or before the printed byte position when a model is cached and the position is known; otherwise it is Moonraker's `current_layer`. `layer.total` is the layer count of the cached model, or Moonraker's `total_layer` when there is none. `heightMm` is the height of the current layer from the cached model, and `objectHeightMm` is the object height from the file metadata. Each is `null` when unknown. `thumbnail` is `true` when the file's metadata lists a thumbnail the relay may fetch and a model key exists (the file's size and modified time are known). It does not promise the image is available now: the thumbnail route can still return `404` during a failed-download backoff or while a download is in flight. The response never contains the filename. Only when `SIGNAL_RELAY_PRINTER_SHOW_FILENAME=true` does it add a `filename` field.

`GET /v1/lab/printer/thumbnail` returns the largest thumbnail of the current job as `image/png`. The relay checks the PNG signature and caps the body at 512 KiB, and it returns `404` when there is no valid thumbnail. A cached thumbnail is served at once. A request that finds another thumbnail download in flight waits at most about 1 second and then returns `404` without recording a failure, so a later request is served from the finished download. Responses are `no-store`.

`GET /v1/lab/printer/model/{modelId}` returns the drawable model of a job the relay has recently seen. The response is `Cache-Control: private, max-age=3600`.

```json
{
  "layerHeight": 0.2,
  "layerCount": 85,
  "bbox": {"minX": 0.0, "minY": 0.0, "maxX": 60.0, "maxY": 40.0},
  "layers": [{"z": 0.2, "paths": [[0, 0, 600, 0, 600, 400, 0, 400, 0, 0]]}]
}
```

Each path is a flat `[x, y, x, y, ...]` polyline in integer units of 0.1 mm. There is one `layers` entry per layer in layer order, so `layers[i]` is layer `i + 1`, and each layer may have no paths. Any `modelId` that is not 32 lowercase hexadecimal characters returns `404`, and so does an unknown or evicted one.

The `modelId` is the first 32 hexadecimal characters of HMAC-SHA256 over the filename, the byte size, and the modified time. The key is a random 32-byte salt that the relay creates once in its storage volume. The identifier is therefore stable across restarts, depends on that salt, and does not reveal the filename. The filename, G-code, and Moonraker responses are never returned or logged.

The relay makes only these upstream requests, through the edge's `8082` listener. A filename must end in `.gcode`, use only ASCII letters, digits, `_`, `-`, `.`, and space, and contain no `..`. Any other name is never requested. `+` is excluded on purpose: the edge accepts only a literal `+` in the metadata query, which Moonraker would decode as a space (the wrong file), and it refuses `%2B`. Such a job still reports state and progress, but it has no model, no thumbnail, and no `objectHeightMm` or `heightMm` from the file. Moonraker's own layer counters still appear.

- `GET /printer/objects/query?print_stats&virtual_sdcard`: at most one call per 5 seconds. Concurrent browser polls share a single call.
- `GET /server/files/metadata?filename=<name>`: cached per filename for 5 minutes, failed reads included. A model needs both `size` and `modified` from the metadata.
- `GET /server/files/gcodes/.thumbs/<name>-<W>x<H>.png`: the path that the metadata reports. It is requested only when it matches `.thumbs/<name>-<W>x<H>.png`, where `W` and `H` are 2 to 4 ASCII digits and the path contains no `..`.
- `GET /server/files/gcodes/<name>.gcode`: at most one download at a time. It is read as a stream and is not retried in a loop.

Models are built in a background task that runs the download and parse in a worker thread. It starts only while a job is `printing` or `paused` and no model is cached for it, and never while idle or complete. The download and parse never run inside a request. Upstream calls never run under the shared lock, which is held only for short in-memory sections. The status poll is single-flight: the request that starts it waits for its own reads, and any request that arrives while it runs waits at most about 1 second for that poll, then answers from the last known snapshot, or with `state: "unavailable"` if there is none yet. A thumbnail request that finds a download in flight waits the same bounded time and then returns `404`, and thumbnail downloads run one at a time. The model route reads its local file under a short lock and makes no upstream call. The poll's reads have a 3-second connect and 10-second read timeout, and a poll that also reads metadata makes a second such call. These are per-socket-operation timeouts, not a total deadline, so a slow body can extend a poll. A read that never completes keeps the status route serving the last known state, and the `updatedAt` field shows its age.

Layers come from `;LAYER_CHANGE` lines and the outer wall from `;TYPE:Outer wall` or `;TYPE:External perimeter`, as written by Orca-, Prusa-, and Bambu-style slicers. The Orca marker has been verified only on synthetic G-code, not on a real sliced file. Cura-style `;LAYER:n` and `;TYPE:WALL-OUTER` markers are not recognized: such a file yields an empty model (`layerCount` 0, no paths, `bbox` null), and `layer.total` is 0.

The G-code is parsed as a stream, one line at a time, and only the extrusion of outer walls is drawn. Travel moves, other features, and arcs (drawn as chords) are left out. Coordinates are quantized to 0.1 mm, repeated points are dropped, and Douglas-Peucker simplification with a 0.2 mm tolerance follows. The file's byte offset of each `;LAYER_CHANGE` line is kept, so a Moonraker `file_position` maps to a layer.

The caps are `150000` drawn points and `2 MiB` of JSON. When a model exceeds either, the tolerance doubles, up to 3.2 mm, before the model is refused. A file is refused whole, never published partially. It has no model, and the progress and layer numbers that Moonraker reports still appear. A file is also refused when it declares more than 150 MB, when a streamed body passes 150 MB, when a line is longer than 16 KiB, when it has more than 5000 layers, when a drawn coordinate is beyond 100 m (`out_of_range`), or when the parser fails on it (`unparseable`). A `404` on the download also rejects it. The refusal is logged with a reason code only. Parsed models are kept on disk for the eight newest jobs. A refused file is remembered in memory for at most 64 files, and it is not downloaded again until the relay restarts or the list evicts it.

The 5-minute backoff is armed when a download starts and is cleared only when the model is stored or the file is finally rejected. A network fault, a non-200 response (including `429`), a truncated body (fewer bytes than its `Content-Length`), or a failed store backs off without rejecting the file, and a failed or truncated download is never cached. A failed thumbnail or metadata read is also not retried for 5 minutes. A download has a 3-second connect timeout and a 30-second idle timeout. A JSON read and a thumbnail read have a 10-second timeout. Thumbnails are capped at 512 KiB, and JSON responses at 256 KiB.

Known limits: no real printer or Moonraker has been tested yet. Parse time and memory use for a 150 MB file on the printer host have not been measured.

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

## Behavior changes

These changes reach existing deployments when they run this relay version. This is the single canonical list; the relay README links here.

- `/v1/lab/home-status` no longer follows Home Assistant redirects, so the Bearer token is never replayed. A redirect now returns `503 home_status_unavailable`.
- A failed `/v1/lab/home-status` refresh is remembered for 30 seconds, so an outage is no longer retried on every public request.
- `SIGNAL_RELAY_HOME_ASSISTANT_*_ENTITY_ID` values are validated at startup. An invalid ID stops the relay with an error that names the setting and never echoes the value.
- Home Assistant reads, including the Meshtastic send projection and broadcast, refuse redirects, cap each response at 1 MiB, and cut off a slow body after 5 seconds.
- Entity domains may start with a digit, as Home Assistant allows.
- Public TCP node URLs additionally reject 6to4, local-use NAT64, Teredo, and router or home-network hostnames such as `.box`, `.router`, `.gateway`, `.modem`, `.wan`, `.domain` and `.mshome.net`.
- The Meshtastic status cache is clamped to at least 900 seconds, as documented. The Meshtastic send projection keeps its 15-second floor.
- Channels publish only when allowlisted in `SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST`. An empty allowlist publishes no channels and omits `channels` entirely, and the entity list is not read.
- The `lastNode` field and `SIGNAL_RELAY_MESHTASTIC_LAST_NODE_ENTITY_ID` are removed. A leftover `SIGNAL_RELAY_MESHTASTIC_LAST_NODE_ENTITY_ID` value is ignored.
- Counts above 100000 are rejected with `503 meshtastic_status_unavailable`, matching the browser's limit.
- A failed channel-list read keeps the counts cached but retries channel discovery after 60 seconds, instead of hiding channels for the full 15-minute window.
- Node IDs written inside published message text are masked the same way as the sender field, so `!52302e42` becomes `!52302e**`. A partial ID cut off at the message limit is dropped.
- Malformed Meshtastic or Home Assistant entity IDs, and invalid channel allowlist, denylist, prefix, or field settings, stop the relay at startup with an error that names the setting and never echoes the value.
- The browser waits up to 20 seconds for the status route, which covers a cold relay refresh. Before, it gave up after 8 seconds and showed the panel as unavailable.
- Direct-message detection is a heuristic. A direct-message channel whose name has no listed token is published only if its name is allowlisted, so keep direct-message channels out of the allowlist and list them in `SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST`.
- The entity list read shares the 1 MiB response cap. On a very large Home Assistant installation the list can be too large, and channels are then omitted while the counts still show `available`. See [docs/MESHTASTIC-INVENTORY.md](MESHTASTIC-INVENTORY.md) step 8 for the workarounds.
- The 3D printer laboratory adds `GET /v1/lab/printer`, `GET /v1/lab/printer/thumbnail`, and `GET /v1/lab/printer/model/{modelId}`. They are disabled by default (`SIGNAL_RELAY_PRINTER_ENABLED=false`), so an existing deployment is unchanged until it enables them with the edge's `8082` listener and allowlist entries in place. Filenames stay private unless `SIGNAL_RELAY_PRINTER_SHOW_FILENAME=true`.

## Deployment

Run Reticulum and the bridge in the Signal Relay Compose project, and Nginx plus the outbound Cloudflare Tunnel in [`destaben/lab-inverse-proxy`](https://github.com/destaben/lab-inverse-proxy). The relay and Nginx join the external `destaben-edge` Docker network; Cloudflared does not. Cloudflared reaches Nginx only over the edge project's internal `172.30.250.0/29` Docker network and uses a separate egress network for its outbound tunnel. Nginx trusts `CF-Connecting-IP` only when the connection comes from Cloudflared's fixed private address, so another container cannot forge the client identity used for limits. The edge reads `CLOUDFLARE_TUNNEL_TOKEN` only from its ignored `.env` file; the relay reads `SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES` and `SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS` only from its own private `.env`, both defaulting to empty mappings. Create the remotely managed tunnel in Cloudflare Zero Trust and map `lab.destaben.dev` to `http://nginx:8080`.

Nginx remains the sole public HTTP policy point. It allowlists the portfolio API routes, permits only their documented `GET`, `HEAD`, `POST`, and CORS `OPTIONS` methods, and returns `404` for any other path or `405` for an unsupported method. The allowlist entry for `GET /v1/lab/meshtastic-status` is part of [`destaben/lab-inverse-proxy` PR #7](https://github.com/destaben/lab-inverse-proxy/pull/7); the public Meshtastic status panel depends on that edge change, not on this repository alone. The browser-facing endpoints deliberately remain anonymous: embedding an API key in the static portfolio would disclose it to every visitor and provide no authentication guarantee. Its internal `8081` listener has no host port or Cloudflare ingress and proxies the relay's fixed Home Assistant reads, Meshtastic state inventory, and fixed Meshtastic broadcast event to `host.docker.internal:8123`; it is not a Home Assistant public proxy. The printer laboratory also needs the edge's internal `8082` listener, reached as `http://nginx:8082`. It has no host port or Cloudflare ingress and proxies only the four fixed Moonraker requests in the printer section. The public `/v1/lab/printer`, `/v1/lab/printer/thumbnail`, and `/v1/lab/printer/model/*` paths need their allowlist entries in that repository before they are live. The page on `info.destaben.dev` calls these routes cross-origin at `lab.destaben.dev` with plain `GET` requests and no custom headers, so the browser sends no preflight. In production the edge decides the CORS header: it drops the relay's `Access-Control-Allow-Origin` and sets its own server-level value for `https://info.destaben.dev`, which the printer routes inherit because they add no header of their own. The relay's CORS middleware (`SIGNAL_RELAY_ALLOWED_ORIGINS`) only matters for local development against the relay directly.

Before deploying the edge, verify that `172.30.250.0/29` does not overlap an existing Docker, LAN, or VPN subnet. If it does, update that subnet, both fixed container addresses, and Nginx's trusted Cloudflared address together. The deployment supports CGNAT through outbound Reticulum `TCPClientInterface` transports and the outbound Cloudflare HTTP tunnel. Cloudflare Tunnel cannot expose arbitrary Reticulum TCP clients; a standard public `TCPServerInterface` would require a reachable public port or a separately operated TCP relay on a VPS. Do not publish the relay HTTP API, Reticulum TCP, Home Assistant, or any other host port. Keep secrets, Home Assistant credentials and entity IDs, Telegram credentials, and Reticulum identities outside Git and rotate tunnel credentials.

An optional `AutoInterface` supports local discovery only. For off-LAN LXMF delivery, configure a trusted Reticulum transport interface that both peers can reach. `services/signal-relay/reticulum-config.example` provides the current public bootstrap transports as the deployment starter. Existing deployments must merge refreshed bootstrap entries into their private `reticulum/config`; they must not replace the Reticulum directory or remove deployment-specific interfaces. When recovering from a broken configuration, replace only `reticulum/config` with the current template and recreate `signal-relay`; preserve `.env`, `lab-sender-reticulum/`, and the `signal-relay-data` volume. Update the edge from its own repository independently. The private node-alias mapping must match the configured interface names before it can report connection transitions. Announcing a destination alone does not create an Internet route.

The supported container image is `ghcr.io/destaben/signal-relay:latest`. It is published for `linux/amd64` and `linux/arm64` by `.github/workflows/publish-signal-relay.yml`. Its Compose file keeps the relay off the host network, exposes no host port, persists Reticulum configuration and service state, and drops Linux capabilities. The separate edge joins the same `destaben-edge` Docker network and routes only explicitly allowed paths. See `services/signal-relay/README.md` and [`destaben/lab-inverse-proxy`](https://github.com/destaben/lab-inverse-proxy) for host setup and updates.

## Acceptance checks

Pull requests also run the relay `pytest` suite and the Compose `config` check through `.github/workflows/ci.yml`; these checks do not replace the host checks below.

1. Restarting the bridge retains the same LXMF destination identity.
2. An incoming LXMF message produces one retained plain-text inbox entry without exposing sender metadata.
3. Rate-limited web signals produce a public rejection code but do not reveal policy internals.
4. The public endpoint exposes no private network, Reticulum, scrape-target, or monitoring configuration details. The laboratory metrics route exposes only its documented aggregate container series.
5. Prometheus captures inbound message counts and the retained inbox size.
6. With Telegram credentials configured, an incoming message produces one private notification; a Telegram failure does not interrupt inbox persistence or LXMF delivery.
7. The Home Assistant and Meshtastic laboratory routes return only their documented delayed aggregate projections; Home Assistant has no public route through `lab.destaben.dev`.
8. The public edge returns `404` for unlisted paths, `405` for unsupported methods, and `429` for requests exceeding the documented per-client limits; the relay, Home Assistant, and Reticulum publish no host ports.
9. With the printer laboratory disabled, its three routes return `404`. When it is enabled, `GET /v1/lab/printer` contains no `filename` unless `SIGNAL_RELAY_PRINTER_SHOW_FILENAME=true`, and the relay's logs contain no filenames or G-code content.
