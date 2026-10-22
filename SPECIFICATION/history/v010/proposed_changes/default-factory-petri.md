---
topic: default-factory-petri
author: claude-opus-5-5
created_at: 2026-10-22T22:16:44Z
---

## Proposal: Default dispatch factory moves from legacy to petri

### Target specification files

- SPECIFICATION/constraints.md

### Summary

Change the ratified `dispatcher.default_factory` value in §"Factory routing" from `legacy` to `petri`, keeping `legacy` as a declared registry-backed entry and leaving the rest of the section unchanged.

### Motivation

Maintainer direction relayed by coordinator session gitops-fleet-capacity-monitoring as ruling R668 moves every fleet repository's dispatch default from the `legacy` Fabro factory to `petri`, the current Fabro server; ruling R672 approves this spec revise as a delegated decision. Work-item bd-ib-iud52v. The committed `.livespec.jsonc` on the same branch adds a registry-backed `petri` entry to `dispatcher.factories` and sets `dispatcher.default_factory` to `petri`, keeping `legacy` declared; the orchestrator's resolver resolves `petri` through the dispatching host's rendered `/etc/livespec/fabro-factories.json` (environment `livespec-ci`). The ratified sentence still names `legacy`, so the spec must move with the configuration.

### Proposed Changes

In `SPECIFICATION/constraints.md` §"Factory routing", replace the final sentence

> `dispatcher.default_factory` MUST name `legacy`.

with

> `dispatcher.default_factory` MUST name `petri`; `legacy` remains a declared registry-backed entry.

Every other sentence of the section — the registry-backed requirement (`"registry": true`, no `server`, no `docker_host`) and the resolution of a registry-backed entry by name from `/etc/livespec/fabro-factories.json` — is unchanged. No `## ` heading is added, renamed or removed.
