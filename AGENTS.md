# Project Instructions

## Context

This repository is the source for `https://info.destaben.dev`. It is a static Astro personal portfolio. GitHub Pages deploys the site from `main` through `.github/workflows/deploy-pages.yml`.

## Structure

- `astro.config.mjs` contains Astro site configuration.
- `src/config/site.ts` contains the site identity and global SEO metadata.
- `src/data/portfolio.ts` contains structured portfolio data.
- `src/components/` and `src/layouts/` contain shared Astro UI and browser-side integration code.
- `src/content/` contains type-checked future content collections.
- `public/` contains static source assets; `public/CNAME` declares the production custom domain.
- `services/signal-relay/` contains the separate FastAPI/LXMF bridge, its tests, Docker image, and Compose deployment manifest.
- `.github/workflows/publish-signal-relay.yml` publishes the relay image to GitHub Container Registry.

## Working Rules

- Use Node 22 LTS and npm. Install CI dependencies with `npm ci`, validate with `npm run check`, build with `npm run build`, and preview with `npm run preview`.
- Do not commit generated `dist/`, `.astro/`, `node_modules/`, coverage, or local environment files.
- Keep `site` set to `https://info.destaben.dev` in `astro.config.mjs`; this is the production canonical URL even though GitHub Pages hosts the site.
- Keep the deployment least-privilege and artifact-based. Changes to deployment behavior must update both the workflow and `README.md`.
- Do not commit credentials, tokens, or non-public personal data to this publicly deployed repository. Any portfolio contact detail must be intentionally public.
- The Signal Relay is not part of GitHub Pages. Keep its Reticulum identity, inbox data, Telegram credentials, tunnel configuration, and deployment `.env` files outside Git.
- Validate relay changes with `services/signal-relay/.venv/bin/python -m pytest`; validate the site with `npm run verify`. Validate Compose with `docker compose -f services/signal-relay/compose.yaml config` using a local, ignored `.env`.
- Keep the relay image compatible with `linux/amd64` and `linux/arm64`, and preserve its loopback-only HTTP binding in Compose. Changes to its public API, container deployment, or security boundary must update `docs/SIGNAL-RELAY.md` and `services/signal-relay/README.md`.
- Do not reintroduce AWS deployment resources. Retired cloud resources must be destroyed only after the GitHub Pages site, DNS, and HTTPS are verified.

## AI Assistance

- Use the scoped instructions in `.github/instructions/` for portfolio, relay, and deployment work. They complement this file; the documented public contracts remain the source of truth.
- Use the `portfolio-content` skill for bilingual portfolio or article changes, and `release-validation` before completing a change.
- Use `portfolio-reviewer` for site, content, accessibility, or localization reviews. Use `relay-boundary-reviewer` for relay API, privacy, Nginx, Compose, or deployment-boundary reviews.
- Invoke `documentation-curator` after implementing every change and before validation or completion. It must update only the documentation and AI context that the diff makes inaccurate, incomplete, or newly necessary.
- Use `change-verifier` to select and run the required checks. Only it may record a completed validation for the local AI guard.
- The AI guard requires confirmation before a sensitive change and blocks completion until the current sensitive diff has matching local validation evidence. Its local state is ignored and never replaces CI.