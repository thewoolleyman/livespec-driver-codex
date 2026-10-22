---
proposal: default-factory-petri.md
decision: accept
revised_at: 2026-10-22T23:07:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted per ruling R668 (maintainer direction relayed by coordinator session gitops-fleet-capacity-monitoring: this repository's dispatch default moves from the `legacy` Fabro factory to `petri`, the current Fabro server) and ruling R672 (this spec revise is approved as a delegated decision); work-item bd-ib-iud52v. The committed .livespec.jsonc on the same branch declares a registry-backed `petri` entry, keeps `legacy` declared and registry-backed, and sets `default_factory` to `petri`; the orchestrator's resolver resolves `petri` through /etc/livespec/fabro-factories.json to the current Fabro server, environment livespec-ci. Only the default-factory sentence of §"Factory routing" changes; no heading moves. In addition to the configured ratification reviewer recorded below, an independent read-only review of the same resulting bytes ran on OpenAI Codex (reviewer model gpt-6-astra, `codex exec -s read-only`), verdict NO BLOCKERS in round 1 of 1 at 2026-10-22T23:07:13Z, over this repository and livespec-driver-claude/livespec-driver-codex together (R677: one review over the identical change).

## Resulting Changes

- constraints.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T23:06:30Z
verdict: NO BLOCKERS
proposal_stem: default-factory-petri
content_digest: 9382017aa08a635230ff98b5a98b01c3abc02316f1379c380951ecf5b56d91f8
