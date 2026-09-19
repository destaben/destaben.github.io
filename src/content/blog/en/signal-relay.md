---
title: "Reticulum: a direct contact point"
description: "The architecture behind a public Reticulum destination, a privacy-preserving inbox, and separate operational metrics."
locale: en
pubDate: 2026-09-19
tags: [Reticulum, SRE, Architecture]
draft: false
---

A static site and a Reticulum node solve different problems. The web must be fast and accessible; the node must be persistent, observable, and protected against abuse.

## Explicit boundaries

A browser is not a Reticulum client. The site should not pretend otherwise or turn a web form into a misleading proxy for direct messaging. A dedicated service uses the official Reticulum implementation to maintain one public delivery destination.

## Architecture

1. GitHub Pages serves the static portfolio.
2. A lab subdomain reaches a bridge through an outbound HTTPS/WSS tunnel.
3. The bridge maintains a persistent Reticulum identity and receives direct messages at its delivery destination.
4. The public panel shares that address and displays only sanitised arrival notices; Prometheus receives operational metrics separately.

The node and bridge do not belong in this repository. Keeping them separate prevents secrets, cryptographic identities, and operational configuration from ending up in a public static deployment.

## Launch bar

The inbox deliberately omits message bodies, titles, and sender identity. Retention is bounded, and monitoring stays in Prometheus rather than becoming a public status display. This keeps the contact surface useful without disclosing private conversations or operational topology.