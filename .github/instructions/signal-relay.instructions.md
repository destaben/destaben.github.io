---
description: "Use when editing the Signal Relay FastAPI service, Reticulum or LXMF integration, Compose, Prometheus, Telegram, Home Assistant, laboratory endpoints, or their Astro consumers."
applyTo: "services/signal-relay/**,docs/SIGNAL-RELAY.md,src/components/SignalRelayLab.astro,src/components/ContainerMetricsLab.astro,src/components/HomeAssistantLab.astro"
---
# Signal Relay Boundary Guidelines

- `docs/SIGNAL-RELAY.md` defines the public contract. Keep the public surface anonymous, bounded, and intentionally small.
- Never expose or log identities, private keys, source hashes, IP addresses, interface or path details, entity IDs, raw Home Assistant values, Prometheus credentials, tunnel configuration, or secrets.
- Public endpoints return fixed projections with bounded input, output, errors, and time ranges. Do not add generic proxying, arbitrary queries, raw metrics, or management endpoints.
- Educational Reticulum sending stays disabled by default. Preserve isolated temporary runtimes, browser-scoped sessions, one-message limits, expiry, actual delivery states, and bounded public error codes.
- `GET /v1/contact` is the only public source of the LXMF destination address. Educational session responses may expose only an opaque session ID, bounded state, error code, expiry, and observed configured public node alias; never expose source or destination hashes. Keep all hash-based delivery correlation internal.
- Nginx and the outbound Cloudflare Tunnel are owned by `destaben/lab-inverse-proxy`. Keep the relay on the external `destaben-edge` network with no host port. The CGNAT deployment uses outbound Reticulum `TCPClientInterface` transports; do not add a `TCPServerInterface`, expose Reticulum TCP, or publish the relay HTTP API, Home Assistant, or any other host port.
- Preserve unprivileged, read-only, capability-dropped containers and `linux/amd64` plus `linux/arm64` image support.
- A public API, deployment, or security-boundary change must update both `docs/SIGNAL-RELAY.md` and `services/signal-relay/README.md` and include focused tests.
- Validate Python changes with `services/signal-relay/.venv/bin/python -m pytest`. For Compose or image changes also run `docker compose -f services/signal-relay/compose.yaml config` with an ignored local `.env`.