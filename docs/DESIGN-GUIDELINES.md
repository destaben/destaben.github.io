# Portfolio Guidelines

## Purpose

The portfolio demonstrates David Estaben's engineering judgement through clear case studies, operational detail, and small, honest technical demonstrations. It is not a product marketing site or a copy of an employer's internal systems.

## Brand

- Use the David Estaben wordmark in site navigation. `/images/site/brand-mark.svg` remains the social asset and `/images/site/favicon.svg` is the small, high-contrast browser icon.
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
- The Home Assistant panel may show only a delayed, rounded aggregate temperature and humidity reading. It must not expose Home Assistant itself, entity IDs, rooms, devices, attributes, histories, presence, cameras, alarms, locks, doors, windows, lights, switches, automations, media, energy use, or network details.
- Web input requires a documented rate limit, input validation, abuse controls, retention period, and kill switch before it is enabled.
- The GitHub Pages site remains static. Persistent APIs and WebSockets live behind a separate, HTTPS-only public endpoint.

## Labs

- Every published lab has a localized title, explicit availability state, and technology tags. The Labs section provides a shared explanation of its purpose and boundaries.
- The Reticulum educational wizard may show a temporary sender hash only to the browser session that created it. It must never imply a real delivery when the relay has not returned one.
- Each non-Reticulum lab needs its own component and public contract. It must not reuse Reticulum endpoints or imply that it runs on the same host.

## Accessibility

- Keep semantic landmarks, visible keyboard focus, skip navigation, and reduced-motion support.
- Validate at mobile and desktop widths. Text, controls, and system panels must not clip or overlap.
- Maintain sufficient contrast for every state, including status indicators.