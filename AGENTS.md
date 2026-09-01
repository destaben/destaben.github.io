# Project Instructions

## Context

This repository is the source for `https://info.destaben.dev`. It is a Hugo personal website using the Toha theme. GitHub Pages deploys the site from `main` through `.github/workflows/deploy-pages.yml`.

## Structure

- `website/config.yaml` contains Hugo and site-wide configuration.
- `website/data/en/` contains the English author, site, and section data.
- `website/assets/` contains site images and other source assets.
- `website/themes/toha` is a Git submodule pinned to Toha `v2.2.0`.
- `website/static/CNAME` declares the production custom domain.

## Working Rules

- Initialize submodules before editing or building: `git submodule update --init --recursive`.
- Use Hugo extended `0.85.0`; it is intentionally matched to Toha `v2.2.0`.
- Build with `hugo --source website --minify`. Use `hugo server --source website --buildDrafts` for local preview.
- Do not commit generated `website/public/`, `website/resources/`, or Hugo lock files.
- Keep `baseURL` set to `https://info.destaben.dev`; this is the production canonical URL even though GitHub Pages hosts the site.
- Keep the deployment least-privilege and artifact-based. Changes to deployment behavior must update both the workflow and `README.md`.
- Do not reintroduce AWS deployment resources. Retired cloud resources must be destroyed only after the GitHub Pages site, DNS, and HTTPS are verified.