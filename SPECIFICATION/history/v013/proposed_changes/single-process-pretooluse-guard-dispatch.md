---
topic: single-process-pretooluse-guard-dispatch
author: claude-opus-5-5:anthropic-burn-mitigation
created_at: 2026-11-02T00:52:10Z
---

## Proposal: Run the Bash-matched PreToolUse guards in one fail-open-per-guard dispatcher process

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Start the Codex Driver's Bash-matched PreToolUse guards (livespec_footgun_guard, block_raw_bd_create, block_auto_memory) through one dispatcher process that evaluates each in-process inside its own fail-open boundary. The deny-iff-any-denies decision and each denying guard's payload stay unchanged. This is the Codex twin of livespec-driver-claude's single-process-pretooluse-guard-dispatch proposal.

### Motivation

Measured on the shared dev host (vmi3006760) on 2026-11-02, plan anthropic-burn-mitigation (livespec-orchestrator-beads-fabro epic bd-ib-b2jzxw, coordinator priority 5: decrease dev-host load). A 60 s bpftrace joined each exiting process's execve argv to its sum_exec_runtime. The Codex Driver's three Bash-matched guards each start their own python3: livespec_footgun_guard 1.7 s, block_auto_memory 1.5 s and block_raw_bd_create 1.1 s of CPU in one minute, about 4.3 CPU-s, almost all of it interpreter start-up. One process per Bash call removes two of the three start-ups. The fail-open-per-guard rule keeps today's guarantee that a broken guard never wedges every tool call. The coordinator asked for this change to be filed in the same pass as the Claude Driver's.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Hook bundle", replace the sentence

> Each script is invoked by the runtime as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<script>.py"` — here the Driver's own plugin-root placeholder IS correct, since the scripts are Driver-owned and live in the Driver bundle, and the substitution works for Codex hooks.

with:

> The runtime MUST start every PreToolUse guard registered on the `Bash` matcher through ONE dispatcher entry point, `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_dispatch.py"`, so one Bash tool call starts one Python process for the Driver's PreToolUse guards rather than one per guard. The dispatcher imports each guard module and evaluates every guard in-process against the same payload. Each guard runs inside its OWN fail-open boundary: a guard that raises, times out or returns a malformed result is treated as an allow for that guard alone and MUST NOT suppress, reorder or alter any other guard's decision, nor turn the tool call into a deny. The dispatcher denies the call iff at least one guard denies it, emitting the `hookSpecificOutput.permissionDecision: "deny"` payload of the first denying guard in registration order, byte-identical to that guard's payload when run standalone; otherwise it emits empty stdout and exits 0. Every other hook is invoked as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<script>.py"`, and each guard script MUST remain runnable standalone by that form with unchanged behaviour. Here the Driver's own plugin-root placeholder IS correct, since the scripts are Driver-owned and live in the Driver bundle, and the substitution works for Codex hooks.

The reconciler's validation of "every declared PreToolUse and Stop Python hook" covers `pretooluse_dispatch.py` as a declared hook and each guard module it imports.

In `SPECIFICATION/scenarios.md`, add after "## Scenario: footgun guard fails open on the dangerous string as data":

## Scenario: one Bash tool call starts one Python process for the Driver's PreToolUse guards

```gherkin
Given the Codex Driver plugin is installed and its hooks are trusted
When the agent makes one Bash tool call
Then the Driver's hooks.json starts exactly one Python process for its Bash-matched PreToolUse guards
And every guard the bundle registers on the Bash matcher is evaluated against that call's payload
```

## Scenario: a crashing guard inside the PreToolUse dispatcher disables neither the other guards nor the tool call

```gherkin
Given one Bash-matched PreToolUse guard of the Driver raises an exception on a payload
When the agent makes a Bash tool call with that payload
Then every other Bash-matched guard is still evaluated against the call
And a deny from any other guard still denies the call with that guard's own payload
And when no other guard denies, the call is allowed with empty stdout and exit 0
```

Co-edit `tests/heading-coverage.json`: add one entry per new scenario heading (`spec_file: "scenarios.md"`, `test: "TODO"`, `reason: "Realized by the PreToolUse dispatcher implementation item filed after this revise; the dispatcher's tests under tests/hooks/ will replace this TODO."`).
