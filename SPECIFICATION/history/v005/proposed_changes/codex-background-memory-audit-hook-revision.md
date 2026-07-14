---
proposal: codex-background-memory-audit-hook.md
decision: accept
revised_at: 2026-07-14T03:05:45Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept: documents the Codex-specific, Driver-owned codex_background_memory_audit.py Stop hook that the repo already ships (wired in livespec/hooks/hooks.json as a second Stop entry). Resolves impl-ahead-of-spec drift in contracts.md §"Hook bundle": corrects the script count (three→four) and the enumeration, adds a paragraph documenting the hook's existence, Stop wiring, and warn-only/read-only posture over ~/.codex/memories_1.sqlite, and amends the closing propose-change-cycle sentence to route disjunctively by ownership so the section stays internally consistent (family-standard hooks → upstream contract; this Codex-specific hook → this tree). All edits confined to contracts.md §"Hook bundle"; no H2 heading added/renamed/removed, so tests/heading-coverage.json needs no co-edit. Independently reviewed by a Fable-model agent: NO BLOCKERS.

## Resulting Changes

- contracts.md
