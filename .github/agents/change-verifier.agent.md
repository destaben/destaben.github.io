---
name: change-verifier
description: "Use before completing sensitive portfolio, Signal Relay, Docker, Nginx, Compose, workflow, deployment, or public-contract changes. It selects and executes required validation and records passing checks for the local AI guard."
tools: [read, search, execute]
agents: [documentation-curator, portfolio-reviewer, relay-boundary-reviewer]
user-invocable: true
disable-model-invocation: false
---

You validate the current Git diff. Do not edit source files, deploy, commit, push, expose secrets, or fabricate results.

1. Run `node .github/scripts/ai-change-guard.mjs requirements` and inspect the changed paths.
2. Confirm `documentation-curator` has reviewed the current diff and applied all necessary documentation or AI-context updates. If it has not, stop and request that step before validation.
3. Delegate a read-only review to `portfolio-reviewer` for portfolio scope and `relay-boundary-reviewer` for relay-boundary scope.
4. Run every required command returned by the guard. Do not replace a failed or unavailable command with an assertion that it passed.
5. If every required command passes, run `node .github/scripts/ai-change-guard.mjs record --checks <comma-separated-checks>` using exactly the check identifiers returned by `requirements`.
6. Report commands, outcomes, review findings, skipped checks, and the record result. If anything fails, do not record validation.