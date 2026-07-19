---
proposal: tmux-default-socket-guard.md
decision: accept
revised_at: 2026-07-19T03:45:00Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Accept: documents the Codex tmux default-socket guard now implemented in
`livespec_footgun_guard.py`. The Driver has a Codex PreToolUse seam for
Bash commands, so the L2 guard path is available and does not need the
documented-gap closure path. The Bash guard now denies the same tmux
hazard class as the Claude guard: unscoped/default `tmux kill-server`,
default/fleet `-S` targets, `pkill`/`killall tmux`, recursive shell `-c`
payloads, and parse-error fail-closed handling for hazard-shaped tmux
commands. `TMUX_TMPDIR` is explicitly not trusted as a scoping control.

## Resulting Changes

- contracts.md
