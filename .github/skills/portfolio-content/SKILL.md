---
name: portfolio-content
description: "Use when creating or revising bilingual portfolio sections, case studies, labs, technical notes, Markdown or MDX posts, public biography, project claims, or localized site copy."
argument-hint: "Describe the content change and its Spanish/English scope"
---

# Portfolio Content

## Procedure

1. Identify the content source: `src/data/portfolio.ts` for the landing portfolio; `src/content/blog/` for posts; `src/config/site.ts` for shared identity and SEO.
2. Update Spanish and English primary content deliberately in the same change. Preserve localized routes and section IDs.
3. For a post, include typed frontmatter: `title`, `description`, `locale`, `pubDate`, optional `updatedDate`, `tags`, and `draft`.
4. State only specific, public, verifiable technical claims. Do not include client data, employer internals, incidents, home-network details, contact secrets, or unreleased metrics.
5. A case study should explain context, constraint, engineering decision, outcome, and technologies. A live panel must state its actual availability or delay.
6. Check generated rendering with `npm run check` and `npm test`. Add or update `tests/site-output.test.mjs` for a route, label, contract, or public rendering guarantee.

## References

- `docs/DESIGN-GUIDELINES.md` is authoritative for public-content, branding, accessibility, and live-service rules.
- `README.md` describes the content collections and publishing behavior.