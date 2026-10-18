---
topic: codex-auto-memory-guard-every-write-route
author: claude-opus-5-5
created_at: 2026-10-18T17:06:30Z
---

## Proposal: Codex auto-memory guard restated for every write route

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Restate this Driver's auto-memory guard to match livespec core v225: registered on Write, Edit, apply_patch and Bash, refusing writes into either agent memory directory in a governed project, reads and rm passing, an identical deny reason whose durable-guidance route names the short AGENTS.md entry plus .ai/<topic>.md shape. Add a scenario for the behaviour.

### Motivation

livespec core v225 (livespec PR 2892) widened the Codex auto-memory-write guard; this repository's implementation landed in PR 789 (livespec-driver-codex-qi5gkw) but SPECIFICATION/contracts.md Hook bundle still describes a Write/Edit guard over ~/.codex/memories/ only, and no scenario covers the guard. Plan block-auto-memory-coverage (epic livespec-driver-claude-22yt6u).

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Hook bundle", the paragraph beginning "A **PreToolUse** guard on `Write` and `Edit` (`block_auto_memory.py`)" MUST be replaced with:

A **PreToolUse** guard (`block_auto_memory.py`), registered on `Write`,
`Edit`, `apply_patch` and the shell tool (`Bash`), that refuses every
write into an agent memory directory — the Codex local-memory store
(`~/.codex/memories/`) or the Claude Code auto-memory layout
(`~/.claude/projects/<slug>/memory/*.md`) — in a livespec-governed
project (one whose `.livespec.jsonc` carries a non-empty
`implementation.plugin`). For a file tool it acts on a target path under
either directory; for a shell command it acts only when it POSITIVELY
identifies a write into one, judging each `;`, `&&`, `||` and pipeline
segment and the payload of a `sh -c` / `bash -c` / `env` wrapper, and
recognising at least the write forms livespec core's §"Driver-shipped
hooks" lists (redirection including a here-document, `tee`, `sed -i`,
`perl -i`, `cp`, `mv`, `install`, `ln`, `touch`, `truncate`, `dd of=`, an
inline interpreter write). A command that only reads such a directory,
or removes a note with `rm`, passes. The deny reason is identical on
every route and routes the would-be write BY INTENT — NOT silently
dropping it — naming four durable destinations: trackable work to the
active impl-plugin's `/<plugin>:capture-work-item` skill (namespace
resolved dynamically from `implementation.plugin`, NEVER hardcoded); a
spec-level rule or behavior to `/livespec:propose-change`; durable agent
guidance / a learned preference / a convention to a short discoverable
`AGENTS.md` entry pointing at a `.ai/<topic>.md` file holding the
content, or to `AGENTS.md` alone when the guidance is short; and only
genuinely session-only, throwaway notes may be dropped. This is the
Codex-runtime sibling of the Claude Driver's `block-auto-memory` guard;
it covers the manual-write and shell-write paths only — KNOWN
LIMITATION: Codex's background-generated primary memories are outside
the pre_tool_use hook lifecycle, so this guard cannot intercept them; a
write whose destination path is computed at runtime is likewise a stated
limit. Governance detection: `CLAUDE_PROJECT_DIR` env var is tried
first, then cwd-walk looking for `.livespec.jsonc`. Fail-open: any
exception, non-match, or missing governance is a silent pass-through,
exit 0; the hook denies ONLY when it POSITIVELY identifies a governed
project and a write into an agent memory directory.

In `SPECIFICATION/scenarios.md` the following scenario MUST be added before `## Scenario: footgun guard fails open on the dangerous string as data`:

## Scenario: auto-memory guard refuses every write route into an agent memory directory

```gherkin
Given a governed project whose .livespec.jsonc declares an implementation.plugin
When a Codex agent writes into ~/.codex/memories/ or a Claude Code memory directory through Write, Edit, apply_patch, or a shell command such as a redirect, tee, sed -i, cp or an inline interpreter write
Then the PreToolUse auto-memory guard emits a hookSpecificOutput.permissionDecision of "deny"
And the deny reason is identical on every route and routes durable guidance to a short AGENTS.md entry pointing at a .ai/<topic>.md file
And a shell command that only reads a memory directory, or removes a note with rm, is not denied
```

`tests/heading-coverage.json` MUST gain a row for the new heading mapped to the subprocess smoke test that drives the shipped guard over its real stdin/stdout protocol.
