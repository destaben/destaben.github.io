# David Estaben's Website

Source for [info.destaben.dev](https://info.destaben.dev), built with Hugo and deployed to GitHub Pages from `main`.

## Requirements

- Git 2.20 or later, with submodule support.
- Hugo extended `0.85.0`. This version is intentionally pinned because the site uses Toha `v2.2.0`.

## Local Development

Clone the repository with its theme:

```sh
git clone --recurse-submodules git@github.com:destaben/destaben.github.io.git
cd destaben.github.io
```

For an existing checkout, initialize the theme with:

```sh
git submodule update --init --recursive
```

Run the development server:

```sh
hugo server --source website --buildDrafts
```

Create the production build:

```sh
hugo --source website --minify
```

The generated files are written to `website/public/` and must not be committed.

## Deployment

Every push to `main` runs `.github/workflows/deploy-pages.yml`. The workflow builds the site with Hugo extended `0.85.0` and deploys the generated artifact to GitHub Pages. GitHub Actions is the only deployment path; do not publish generated files to a branch.

In the repository settings, configure Pages to use **GitHub Actions** as its source. The published artifact includes `website/static/CNAME`, which declares `info.destaben.dev` as the custom domain.

## Custom Domain

Set the Pages custom domain to `info.destaben.dev`, then create this DNS record at the authoritative DNS provider:

```text
info.destaben.dev CNAME destaben.github.io
```

Use DNS-only mode for this CNAME. Wait for GitHub to verify DNS and issue its certificate before enforcing HTTPS.