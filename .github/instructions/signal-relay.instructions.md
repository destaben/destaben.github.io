---
description: "Use when editing the Signal Relay FastAPI service, Reticulum or LXMF integration, Nginx, Compose, Prometheus, Telegram, Home Assistant, laboratory endpoints, or their Astro consumers."
applyTo: "services/signal-relay/**,docs/SIGNAL-RELAY.md,src/components/SignalRelayLab.astro,src/components/ContainerMetricsLab.astro,src/components/HomeAssistantLab.astro"
---
# Signal Relay Boundary Guidelines

- `docs/SIGNAL-RELAY.md` defines the public contract. Keep the public surface anonymous, bounded, and intentionally small.
- Never expose or log identities, private keys, source hashes, IP addresses, interface or path details, entity IDs, raw Home Assistant values, Prometheus credentials, tunnel configuration, or secrets.
- Public endpoints return fixed projections with bounded input, output, errors, and time ranges. Do not add generic proxying, arbitrary queries, raw metrics, or management endpoints.
- Educational Reticulum sending stays disabled by default. Preserve isolated temporary runtimes, browser-scoped sessions, one-message limits, expiry, actual delivery states, and bounded public error codes.
- Keep Nginx as the sole public policy point, retain the loopback-only host binding, and do not expose Reticulum or Home Assistant ports.
- Preserve unprivileged, read-only, capability-dropped containers and `linux/amd64` plus `linux/arm64` image support.
- A public API, deployment, or security-boundary change must update both `docs/SIGNAL-RELAY.md` and `services/signal-relay/README.md` and include focused tests.
- Validate Python changes with `services/signal-relay/.venv/bin/python -m pytest`. For Docker, Nginx, Compose, or image changes also run `docker compose -f services/signal-relay/compose.yaml config` with an ignored local `.env`.