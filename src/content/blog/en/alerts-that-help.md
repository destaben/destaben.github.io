---
title: "Alerts that help teams decide"
description: "A practical way to turn technical signals into alerts that guide a response instead of adding noise."
locale: en
pubDate: 2026-09-19
tags: [SRE, Observability, Operations]
draft: false
---

An alert is not a graph in a hurry. It is a request for attention that interrupts someone, and it needs to justify that interruption. The useful question is not “can we measure it?”, but “what decision will we make when it happens?”.

## Start with impact

A high CPU signal can be interesting; an alert should connect that signal to a consequence. For example: “the error rate has exceeded 2% for ten minutes and is already affecting a critical path.” The second case gives the person on call a priority, a time window, and somewhere to begin investigating.

Before creating an alert, I try to write one complete sentence:

> If this condition persists, a user or team will lose a specific capability, and we should make this first check.

If that sentence does not come easily, we may still have a metric to observe rather than an alert to respond to.

## Three pieces of context

An operational alert becomes far more useful when it includes:

1. **What changed:** the service, dependency, or indicator that moved out of bounds.
2. **Who is affected:** the user journey, region, or team experiencing the problem.
3. **What to try first:** a query, dashboard, or reversible action that reduces uncertainty.

Not every notification needs an encyclopaedic runbook. A link to the right panel and one testable first hypothesis are usually more useful than a long list of possibilities.

## Treat noise as a design failure

Alerts that no one opens, closes without looking, or receives during planned maintenance teach us something about the system. Review them with the same calm as an incident: does the threshold represent real harm, does the window avoid brief spikes, is ownership clear, and is the alert still needed?

Removing an alert is not lowering vigilance. It reserves human attention for signals that can change the outcome of a situation.