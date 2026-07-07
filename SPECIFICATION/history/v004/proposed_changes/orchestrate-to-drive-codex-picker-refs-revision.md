---
proposal: orchestrate-to-drive-codex-picker-refs.md
decision: accept
revised_at: 2026-07-07T00:25:47Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Ratify the orchestrate->drive orchestrator-skill rename across the three governed-spec Codex-picker references (spec.md Public surface, scenarios.md /skills-picker scenario, non-functional-requirements.md check-codex-skill-picker). The shipped livespec-orchestrator-beads-fabro plugin now exposes a `drive` skill and no longer exposes `orchestrate` (design record: livespec-orchestrator-beads-fabro design.md; landed history/v031, PR #345; driver-claude BR1). Independent Fable review: NO-BLOCKERS. Plugin name preserved verbatim; no `## ` heading change.

## Resulting Changes

- spec.md
- scenarios.md
- non-functional-requirements.md
