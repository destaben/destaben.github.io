---
name: release-validation
description: "Use before completing, reviewing, or releasing changes to the Astro portfolio, Signal Relay, public API, Docker, Nginx, Compose, GitHub Actions, or deployment documentation."
argument-hint: "Provide the paths changed or ask to validate the current diff"
---

# Release Validation

## Select Checks By Scope

| Changed area | Required checks |
| --- | --- |
| Portfolio, content, Astro, public assets, Pages, or workflows | `npm run verify` |
| Signal Relay Python, API contract, or lab consumer | `services/signal-relay/.venv/bin/python -m pytest` |
| Dockerfile, Compose, Nginx, or image publication | Pytest plus `docker compose -f services/signal-relay/compose.yaml config` with ignored local `.env` |
| AI instructions, skills, agents, hooks, or guard scripts | `node .github/scripts/validate-ai-context.mjs` |
| Frontend and relay contract together | All applicable checks plus a local demo smoke test |

## Local Demo Smoke Test

1. Start Astro at `127.0.0.1:4321` and the relay in explicitly labelled `demo` mode at `127.0.0.1:8787`.
2. Confirm unavailable states are truthful when a protected backend is not configured.
3. Use `POST /v1/demo/inbox` only in demo mode to check the inbox projection. Do not use secrets or claim a Reticulum delivery occurred.
4. For an AI-guarded change, invoke `change-verifier`; it records passing checks against the current diff fingerprint.

## Reporting

Report each command run, its result, checks not run, and any manual verification. A passing local record never replaces the GitHub Actions deployment checks.