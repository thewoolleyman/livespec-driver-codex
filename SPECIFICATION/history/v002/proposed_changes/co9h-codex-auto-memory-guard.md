---
topic: co9h-codex-auto-memory-guard
author: claude-sonnet-4-6
created_at: 2026-06-26T06:53:32Z
---

## Proposal: co9h-codex-auto-memory-guard

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Document the new block_auto_memory.py PreToolUse hook in § Hook bundle: the bundle now carries THREE hooks, not two.

### Motivation

The co9h epic adds a Codex-runtime sibling to the Claude Driver's block-auto-memory guard. The new block_auto_memory.py intercepts Write/Edit tool calls targeting ~/.codex/memories/ in a livespec-governed project and denies with an intent-routing reason. The contracts.md § Hook bundle still says two fail-open scripts and The bundle carries TWO hooks — this is now incorrect.

### Proposed Changes

§ Hook bundle MUST be updated: (1) the opening sentence MUST say three fail-open scripts naming all three; (2) The bundle carries TWO hooks MUST become THREE hooks; (3) a new PreToolUse hook paragraph MUST be added between the footgun guard and the Stop hook documenting block_auto_memory.py.
