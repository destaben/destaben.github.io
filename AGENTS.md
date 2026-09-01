# Project Instructions

## Context

This repository is the source for `https://info.destaben.dev`. It is a static Astro personal portfolio. GitHub Pages deploys the site from `main` through `.github/workflows/deploy-pages.yml`.

## Structure

- `astro.config.mjs` contains Astro site configuration.
- `src/config/site.ts` contains the site identity and global SEO metadata.
- `src/data/portfolio.ts` contains structured portfolio data.
- `src/content/` contains type-checked future content collections.
- `public/` contains static source assets; `public/CNAME` declares the production custom domain.

## Working Rules

- Use Node 22 LTS and npm. Install CI dependencies with `npm ci`, validate with `npm run check`, build with `npm run build`, and preview with `npm run preview`.
- Do not commit generated `dist/`, `.astro/`, `node_modules/`, coverage, or local environment files.
- Keep `site` set to `https://info.destaben.dev` in `astro.config.mjs`; this is the production canonical URL even though GitHub Pages hosts the site.
- Keep the deployment least-privilege and artifact-based. Changes to deployment behavior must update both the workflow and `README.md`.
- Do not commit credentials, tokens, or non-public personal data to this publicly deployed repository. Any portfolio contact detail must be intentionally public.
- Do not reintroduce AWS deployment resources. Retired cloud resources must be destroyed only after the GitHub Pages site, DNS, and HTTPS are verified.