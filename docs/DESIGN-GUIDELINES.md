# Portfolio Guidelines

## Purpose

The portfolio demonstrates David Estaben's engineering judgement through clear case studies, operational detail, and small, honest technical demonstrations. It is not a product marketing site or a copy of an employer's internal systems.

## Brand

- Use the David Estaben wordmark in site navigation, with a localized accessible name. `/images/site/brand-mark.svg` remains the social asset and `/images/site/favicon.svg` is the small, high-contrast browser icon.
- Do not use a personal portrait.
- Preserve the high-contrast palette: ink `#0b1f23`, paper `#f2eee4`, lime `#d8f04b`, and coral `#ff7955`.
- Use display typography only for headings and monospaced text only for operational labels, identifiers, timestamps, and status.

## Content

- Publish all primary content in Spanish and English. Translate deliberately; do not render machine translations at runtime.
- A case study must cover context, constraint, engineering decision, outcome, and technologies. Use measured results only when they are public and verifiable.
- Describe employers and projects at an appropriate public level. Never publish internal topology, client data, incidents, credentials, private source code, or unreleased metrics.
- Link featured work to source code, a live demo, or a technical write-up whenever one can be shared safely.

## Live Services

- A live panel must identify whether the data is live, delayed, simulated, unavailable, or under maintenance. The Reticulum panel uses a green or red availability indicator based on its public health endpoint.
- The Reticulum contact panel may show the public destination and the newest bounded plain-text messages. Treat every displayed message as public; do not expose sender identities, source hashes, private dashboards, monitoring internals, or home-network management endpoints.
- The Reticulum panel may show cards for configured TCP connections only when the fixed node projection is available. Each card may contain the configured public alias, intentionally published `tcp://host:port` URL, and `up` or `down` state. It must not show interface names, private addresses, paths, route details, or suggest that a node state guarantees a route or delivery.
- The Home Assistant panel may show only a delayed, rounded aggregate temperature and humidity reading. It must not expose Home Assistant itself, entity IDs, rooms, devices, attributes, histories, presence, cameras, alarms, locks, doors, windows, lights, switches, automations, media, energy use, or network details.
- The Meshtastic status panel may show only its explicit availability state, delayed aggregate online and total node counts, refresh time, and, for each channel named in the operator's allowlist (at most 16), its name and its single last public message with the sender node ID masked, the message time, and hops when available. Node IDs written inside that message text are masked the same way. The panel shows no full node IDs, locations, telemetry, direct-message channels or their names, and no Home Assistant entity IDs or entity names. Treat every displayed message as public; the panel must say so and point to the page's contact links for removal requests, without showing an address. It must never show direct messages or their names, and must not expose gateway or entity identifiers, full node identifiers, author names or nicknames, serial numbers, MAC addresses, locations, telemetry, older messages, attributes, timestamps other than message times, Home Assistant controls, or sending controls.
- The Meshtastic send panel is the only Meshtastic web input. It is governed by the Turnstile, cooldown, and input-validation rules in [docs/SIGNAL-RELAY.md](SIGNAL-RELAY.md) and must not be presented as available until those controls are deployed.
- Web input requires a documented rate limit, input validation, abuse controls, retention period, and kill switch before it is enabled.
- The GitHub Pages site remains static. Persistent APIs and WebSockets live behind a separate, HTTPS-only public endpoint.

## Labs

- Every published lab has a localized title, explicit availability state, and technology tags. The Labs section provides a shared explanation of its purpose and boundaries.
- The Reticulum educational wizard may show only its opaque session ID, bounded state, error code, expiry, and observed public node alias. It must never expose source or destination hashes, or imply a real delivery when the relay has not returned one.
- Each non-Reticulum lab needs its own component and public contract. It must not reuse Reticulum endpoints or imply that it runs on the same host.

## Accessibility

- Keep semantic landmarks, visible keyboard focus, skip navigation, and reduced-motion support.
- Decorative motion (the hero graphic, its ASCII core, and the section-label scramble) must be `aria-hidden` or backed by real text, and must never carry information the page does not also state in text.
- Every motion effect respects `prefers-reduced-motion`: the page shows its final text and the static fallback, and no animation or WebGL context starts. Effects also pause when they are off-screen.
- WebGL is limited to the hero core island, which shows the static "DE" without WebGL 2 or on narrow screens. Do not add other WebGL, third-party scripts, or animation libraries beyond `motion` for the section labels.
- Validate at mobile and desktop widths. Text, controls, and system panels must not clip or overlap.
- Maintain sufficient contrast for every state, including status indicators.