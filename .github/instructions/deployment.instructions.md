---
description: "Use when editing GitHub Actions workflows, GitHub Pages deployment, CNAME, Astro deployment configuration, Signal Relay image publishing, Docker build, or release documentation."
applyTo: ".github/workflows/**,astro.config.mjs,public/CNAME,README.md,services/signal-relay/Dockerfile,services/signal-relay/compose.yaml"
---
# Deployment Guidelines

- Keep `site` set to `https://info.destaben.dev` in `astro.config.mjs`; it is the canonical URL.
- GitHub Actions is the only Pages publishing path. Preserve artifact-based deployment, least-privilege permissions, Node 22, and the existing CI checks.
- Keep the Pages artifact free of generated files committed to Git. Update `README.md` with any deployment behavior change.
- Keep Signal Relay image publication multi-architecture for `linux/amd64` and `linux/arm64` with provenance enabled.
- Preserve the relay's loopback-only Nginx host binding and separate tunnel sidecar. Do not add AWS deployment resources.
- For relay deployment or security changes, update both relay documents and run the Compose configuration check using only ignored local configuration.