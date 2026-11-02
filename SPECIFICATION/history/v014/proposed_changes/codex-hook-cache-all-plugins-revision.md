---
proposal: codex-hook-cache-all-plugins.md
decision: accept
revised_at: 2026-11-02T15:26:27Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:codex-plugin-hook-path-regression
---

## Decision and Rationale

Accepted as proposed. Generalizes Codex hook-cache compatibility from the Driver's own payload to every hook-declaring plugin installed from a Codex-registered marketplace: covered plugins derived from measured configuration and cache state, hook discovery from the manifest entry and the default hooks/hooks.json, interpreter-agnostic ${CLAUDE_PLUGIN_ROOT}/ entrypoint validation with loud per-plugin failure, per-plugin isolation of version-state and observer status, and a shipped service-supervisor definition for the observer. Drift repairs: the hooks.json description-key rule is scoped to the Driver's own bundle without a claim about Codex's parser; test-discipline and enforcement-suite wording now cover each covered plugin. tests/heading-coverage.json gains an integration-tier TODO entry for the new scenario owned by livespec-driver-codex-esytmj, registered in the regenerated tests/heading-coverage-debt.json. The existing Driver scenario is unchanged. Delegated decision: accept directed by the dispatching coordinator for plan codex-plugin-hook-path-regression; an independent read-only Sonnet ratification reviewer returned NO BLOCKERS on this exact digest.

## Resulting Changes

- contracts.md
- constraints.md
- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T15:26:24Z
verdict: NO BLOCKERS
proposal_stem: codex-hook-cache-all-plugins
content_digest: 1af23082de3dd6ad9206120457555d99fab4427f8d09e8e2b889e84d8746e75a
