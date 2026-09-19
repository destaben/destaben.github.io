---
description: "Use when editing Astro pages, components, styles, portfolio content, blog posts, public assets, SEO, accessibility, localization, or generated-site tests."
applyTo: "src/**,tests/**,public/**,astro.config.mjs"
---
# Astro Portfolio Guidelines

- Preserve the static GitHub Pages architecture. Browser code may consume only documented HTTPS public endpoints.
- Keep primary portfolio content deliberately equivalent in Spanish and English. Update `src/data/portfolio.ts` together; do not add runtime machine translation.
- Use the existing typed content model, shared layouts, and components. Put a new lab in its own component and give it a separate documented public contract.
- Preserve semantic landmarks, the skip link, keyboard focus, reduced-motion support, contrast, and responsive layouts without clipping or overlap.
- Keep canonical URLs and metadata centralized in `src/config/site.ts` and `src/layouts/BaseLayout.astro`.
- Live panels must show an explicit live, delayed, simulated, unavailable, or maintenance state. Never imply a delivery or live value the service has not confirmed.
- Do not publish internal topology, employer details, personal-network details, raw monitoring data, or secrets. `docs/DESIGN-GUIDELINES.md` is authoritative for public-content and live-service boundaries.
- Add generated-output assertions in `tests/site-output.test.mjs` when a route, public contract, localized label, or critical rendering behavior changes.
- Validate site changes with `npm run verify`.