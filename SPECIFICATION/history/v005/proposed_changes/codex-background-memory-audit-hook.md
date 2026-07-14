---
topic: codex-background-memory-audit-hook
author: claude-opus-4-8
created_at: 2026-07-14T02:48:53Z
---

## Proposal: codex-background-memory-audit-hook

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Document the Codex-specific `codex_background_memory_audit.py` Stop hook in contracts.md §"Hook bundle". The Driver already ships this hook (wired in `livespec/hooks/hooks.json` as a second `Stop` entry), but the spec's §"Hook bundle" still enumerates only three scripts and says the bundle carries THREE hooks. This ADDS documentation of the one Codex-specific, Driver-owned hook: its existence, its `Stop` wiring, and its warn-only/read-only posture over Codex's background-memory SQLite store `~/.codex/memories_1.sqlite`. It updates the section's own internal count (three→four) so the exhaustive enumeration in §"Hook bundle" stays accurate, and it amends the section's closing propose-change-cycle sentence to route by ownership (the family-standard hooks flow through the upstream contract; this Codex-specific hook flows through this tree) so the section stays internally consistent. All edits stay within contracts.md §"Hook bundle"; the non-exhaustive bundle summaries in spec.md and non-functional-requirements.md are left unchanged.

### Motivation

Impl-ahead-of-spec drift: the repo ships `livespec/hooks/codex_background_memory_audit.py`, registered in `livespec/hooks/hooks.json` as a second `Stop` hook, but contracts.md §"Hook bundle" documents only `livespec_footgun_guard.py`, `block_auto_memory.py`, and `no_shadow_ledger.py` ("three fail-open scripts", "The bundle carries THREE hooks"). Unlike those three family-standard hooks — whose behavioral postures are owned upstream by livespec core — this hook is Codex-SPECIFIC and Driver-owned: it has NO `livespec-driver-claude` sibling and no upstream posture owner, so THIS repo's spec is its documentation home. Scoped to this one hook only. contracts.md §"Hook bundle" is the exhaustive-enumeration home for the bundle's hooks; the bundle references in spec.md §"This repo ships exactly three things" (item 2) and non-functional-requirements.md §"Repo layout" are intentionally non-exhaustive high-level summaries (item 2 names only the footgun guard, as an exemplar), so they are correct-by-design and need no change here.

### Proposed Changes

All edits are confined to `SPECIFICATION/contracts.md` §"Hook bundle". No `## ` heading is added, renamed, or removed, so `tests/heading-coverage.json` needs no co-edit.

**Change 1 — update the script count and the script list in the section's opening paragraph.**

Replace this verbatim target:

```
The Driver SHIPS a Codex hook bundle at `livespec/hooks/`: a `hooks.json`
registration plus three fail-open scripts — the `livespec_footgun_guard.py`
PreToolUse guard, the `block_auto_memory.py` PreToolUse guard, and the
`no_shadow_ledger.py` Stop hook.
```

with:

```
The Driver SHIPS a Codex hook bundle at `livespec/hooks/`: a `hooks.json`
registration plus four fail-open scripts — the `livespec_footgun_guard.py`
PreToolUse guard, the `block_auto_memory.py` PreToolUse guard, the
`no_shadow_ledger.py` Stop hook, and the `codex_background_memory_audit.py`
Stop hook.
```

**Change 2 — update the internal hook count.**

Replace this verbatim target:

```
The bundle carries THREE hooks.
```

with:

```
The bundle carries FOUR hooks.
```

**Change 3 — add a new hook paragraph documenting the Codex-specific Stop hook.**

Insert the following NEW paragraph immediately AFTER the `no_shadow_ledger.py` Stop-hook paragraph — whose final two lines read, with the live file's exact wrapping:

```
implementation detail and MAY be tuned without a core spec cycle, per the
upstream contract, provided the WARN-only Stop posture holds.
```

— and immediately BEFORE the `Trust model:` paragraph, whose first line reads:

```
Trust model: Codex prompts once to trust a plugin's hooks in interactive
```

The inserted paragraph:

```
A second **Stop** hook (`codex_background_memory_audit.py`) that WARNS —
never blocks — when Codex's background-generated memory store is populated
in a livespec-governed project. It closes the gap the `block_auto_memory.py`
KNOWN LIMITATION names: Codex generates PRIMARY (background) memories
outside the PreToolUse lifecycle, so the manual-write guard cannot
intercept them; this Stop hook AUDITS them at session Stop instead. It
opens the background-memory SQLite store — `~/.codex/memories_1.sqlite` by
default, overridable via the `LIVESPEC_CODEX_BACKGROUND_MEMORY_DB` env var
— in READ-ONLY mode (a `mode=ro` SQLite URI) and NEVER writes to it. It
passes SILENTLY (empty stdout, exit 0) when the store is missing, empty,
malformed, carries none of the expected tables, or the project is not
livespec-governed. When the store carries entries in a governed project it
emits a single `{"systemMessage": ...}` advisory naming the store path and
its row counts, routing anything durable BY INTENT to the same four
destinations `block_auto_memory.py` names (trackable work to the active
impl-plugin's `/<plugin>:capture-work-item`, namespace resolved
dynamically from `.livespec.jsonc` `implementation.plugin`; a spec-level
rule to `/livespec:propose-change`; durable guidance / a learned
preference / a convention to `AGENTS.md` or a focused `.ai/<topic>.md` file
it references; only genuinely session-only notes may be dropped).
Governance detection matches `block_auto_memory.py`: `CLAUDE_PROJECT_DIR`
first, then a cwd-walk for `.livespec.jsonc`. WARN-ONLY and fail-open: it
NEVER emits a blocking `decision`, NEVER exits non-zero, NEVER auto-edits,
and treats malformed stdin, `stop_hook_active` re-entry, and any exception
as a silent exit-0 pass-through. Unlike the family-standard
`livespec_footgun_guard.py`, `block_auto_memory.py`, and
`no_shadow_ledger.py` hooks — whose behavioral disciplines and postures
are owned upstream by `livespec/SPECIFICATION/contracts.md` — this hook is
Codex-SPECIFIC, Driver-owned surface with NO `livespec-driver-claude`
sibling and no upstream posture owner: its existence, its `Stop` wiring in
`hooks.json`, and its warn-only/read-only posture are all governed by THIS
repo's spec. Its mechanical detection internals (the background-store
path, the SQLite table set, the warning-message shape) are Driver
implementation detail and MAY be tuned without a spec cycle, provided the
WARN-only, read-only Stop posture holds.
```

**Change 4 — resolve the internal contradiction in the section's closing paragraph.**

The current closing paragraph routes every hook-posture change through "the upstream contract". That is correct for the three family-standard hooks but contradicts the new Change 3 paragraph, which states the Codex-specific `codex_background_memory_audit.py` hook has no upstream owner and is governed by THIS tree. Route the sentence disjunctively by ownership — mirroring the disjunctive "against this tree … or against core …" intent already used in spec.md §"Lifecycle and evolution".

Replace this verbatim target (the section's full closing paragraph):

```
Adding or removing a hook, renaming a hook surface, or changing the
hook's posture requires a propose-change cycle against the upstream
contract; the mechanical detection internals
(segment tokenization, the primary-checkout probe) are Driver
implementation detail and MAY be tuned without a spec cycle, provided the
postures hold.
```

with:

```
Adding or removing a hook, renaming a hook surface, or changing a hook's
posture requires a propose-change cycle, routed by ownership: for the
family-standard `livespec_footgun_guard.py`, `block_auto_memory.py`, and
`no_shadow_ledger.py` hooks — whose postures are owned upstream — the cycle
runs against the upstream `livespec/SPECIFICATION/contracts.md`; for the
Codex-specific, Driver-owned `codex_background_memory_audit.py` hook, which
has no upstream posture owner, the cycle runs against THIS tree. The
mechanical detection internals
(segment tokenization, the primary-checkout probe) are Driver
implementation detail and MAY be tuned without a spec cycle, provided the
postures hold.
```

