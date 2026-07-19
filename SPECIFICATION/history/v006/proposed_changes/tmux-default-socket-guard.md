---
topic: tmux-default-socket-guard
author: claude-fable-5
created_at: 2026-07-19T03:40:00Z
---

## Proposal: tmux-default-socket-guard

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Document the Codex Bash PreToolUse guard's tmux default-socket denial
class in `contracts.md` §"Hook bundle". Codex agents share the host tmux
socket namespace, so the Driver's existing hook seam must deny unscoped
or default-scoped tmux fleet-kill commands before execution.

### Motivation

The repo already specifies the Codex hook bundle and the
`livespec_footgun_guard.py` Bash PreToolUse posture, but its exhaustive
hazard list omitted the tmux default-socket hazard class. That left the
implemented guard behavior ahead of the dogfooded spec and obscured the
fact that Codex has a usable pre-execution seam for this work item.

### Proposed Changes

Update `SPECIFICATION/contracts.md` §"Hook bundle" so the Bash
PreToolUse guard's never-legitimate denial list includes Codex tmux
fleet-kill hazards in the shared host socket namespace:

- `tmux kill-server` without explicit non-default `-L`/`-S` scoping;
- `tmux -L default kill-server`;
- default/fleet `-S` socket targets;
- `pkill` or `killall` targeting `tmux`;
- recursive shell `-c` / `-lc` payloads carrying those hazards.

State that `TMUX_TMPDIR` is not trusted as a scoping control. Preserve
the guard's exit-0 posture, while documenting the tmux-specific
fail-closed parse behavior for commands that contain a tmux kill hazard
but cannot be parsed safely.
