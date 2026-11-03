# scenarios.md — livespec-driver-codex

Gherkin scenarios for each Driver-owned contract path in `contracts.md`.
These are the worked examples the structural gate, the hook bundle, and
the resolution algorithm are checked against.

## Scenario: installed Driver exposes the eight livespec:* commands

```gherkin
Given a project that enables livespec core and the livespec-driver-codex plugin
When the Codex runtime loads the Driver plugin
Then the eight skills livespec:seed, livespec:propose-change,
  livespec:critique, livespec:revise, livespec:doctor,
  livespec:prune-history, livespec:next, and livespec:help are available
And they are invoked by name under the plugin name "livespec"
```

## Scenario: /skills picker exposes plugin skills by short name

```gherkin
Given the livespec Driver and livespec-orchestrator-beads-fabro plugins are installed
And the operator opens the Codex TUI
When the operator opens "/skills"
And chooses "List skills"
And searches for "drive"
Then the picker renders "drive (livespec-orchestrator-beads-fabro)"
And the rendered row is typed as a Skill
And the operator does not need to search for the colon-qualified
  "livespec-orchestrator-beads-fabro:drive" form
```

## Scenario: core-root resolution via operator override

```gherkin
Given the environment variable LIVESPEC_CORE_PLUGIN_ROOT is set to a core checkout
When a binding resolves <core-root>
Then it uses the override path
And it does not consult the governed-project or installed-cache fallbacks
```

## Scenario: core-root resolution falls back to the governed-project checkout

```gherkin
Given LIVESPEC_CORE_PLUGIN_ROOT is unset
And the governed project IS the livespec core repo loaded with --plugin-dir .
When a binding resolves <core-root>
Then it uses <project-root>/.claude-plugin/
```

## Scenario: core-root resolution falls back to the installed cache

```gherkin
Given LIVESPEC_CORE_PLUGIN_ROOT is unset
And the governed project is not the livespec core repo
When a binding resolves <core-root>
Then it reads the installed livespec@livespec plugin's source.path
  from "codex plugin list --json -m livespec"
```

## Scenario: structural check rejects a SKILL.md invoking uv run

```gherkin
Given a SKILL.md whose fenced wrapper invocation uses "uv run"
When check_plugin_structure runs
Then it exits non-zero
And it emits a violation naming the file and line
```

## Scenario: structural check rejects the Driver's own plugin-root placeholder for core scripts

```gherkin
Given a SKILL.md whose fenced wrapper invocation resolves a bin/<name>.py
  through the Driver's own plugin-root placeholder
When check_plugin_structure runs
Then it exits non-zero
And it reports that the placeholder resolves to the Driver root, which has no scripts/
```

## Scenario: structural check rejects an extra or missing skill directory

```gherkin
Given the skills/ directory is missing one of the eight bindings, or carries an extra directory
When check_plugin_structure runs
Then it exits non-zero
And it names the missing or unexpected skill directory
```

## Scenario: structural check rejects a binding body carrying a Claude marker

```gherkin
Given a SKILL.md body that uses the "/livespec:" slash form, references
  installed_plugins.json, or names livespec-driver-claude
When check_plugin_structure runs
Then it exits non-zero
And it reports the Claude-runtime marker the Codex binding must not carry
```

## Scenario: marketplace description drift is rejected

```gherkin
Given marketplace.json's single plugin entry description differs from plugin.json's description
When check_plugin_structure runs
Then it exits non-zero
And it reports that the marketplace description must duplicate plugin.json's verbatim
```

## Scenario: footgun guard denies a never-legitimate command

```gherkin
Given a Bash tool call whose executed leading command is a footgun
  (git commit/push --no-verify, a leading LEFTHOOK=0/false assignment,
   git config core.bare <true>, or a redirect/tee/sed -i writing into a
   livespec primary checkout)
When the PreToolUse footgun guard runs
Then it emits a hookSpecificOutput.permissionDecision of "deny"
And the deny reason names the correct alternative
And it exits 0
```

## Scenario: auto-memory guard refuses every write route into an agent memory directory

```gherkin
Given a governed project whose .livespec.jsonc declares an implementation.plugin
When a Codex agent writes into ~/.codex/memories/ or a Claude Code memory directory through Write, Edit, apply_patch, or a shell command such as a redirect, tee, sed -i, cp or an inline interpreter write
Then the PreToolUse auto-memory guard emits a hookSpecificOutput.permissionDecision of "deny"
And the deny reason is identical on every route and routes durable guidance to a short AGENTS.md entry pointing at a .ai/<topic>.md file
And a shell command that only reads a memory directory, or removes a note with rm, is not denied
```

## Scenario: footgun guard fails open on the dangerous string as data

```gherkin
Given a Bash tool call carrying a dangerous string as DATA (an echo, a
  git config --get read, or a redirect to a non-primary path), OR a
  stdin payload that is empty, non-JSON, or names a non-Bash tool
When the PreToolUse footgun guard runs
Then it emits no deny decision
And it exits 0 (fail-open)
```

## Scenario: commit at the primary checkout is refused

```gherkin
Given the current checkout's toplevel equals the configured livespec.primaryPath
When a commit or push is attempted
Then the commit-refuse hook exits 1
And it directs the contributor to use a worktree
```

## Scenario: one Bash tool call starts one Python process for the Driver's PreToolUse guards

```gherkin
Given the Codex Driver plugin is installed and its hooks are trusted
When the agent makes one Bash tool call
Then the Driver's hooks.json starts exactly one Python process for its Bash-matched PreToolUse guards
And every Bash-matched guard the bundle carries is evaluated against that call's payload
```

## Scenario: a crashing fail-open guard inside the PreToolUse dispatcher disables neither the other guards nor the tool call

```gherkin
Given one fail-open Bash-matched PreToolUse guard of the Driver raises an exception on a payload
When the agent makes a Bash tool call with that payload
Then every other Bash-matched guard is still evaluated against the call
And a deny from any other guard still denies the call with that guard's own payload
And when no other guard denies, the call is allowed with empty stdout and exit 0
```

## Scenario: a dispatcher that fails before evaluating its guards falls back to the standalone guards

```gherkin
Given the PreToolUse dispatcher fails before it has evaluated every Bash-matched guard
When the agent makes a Bash tool call
Then each not-yet-evaluated Bash-matched guard runs as its own standalone process against that call's payload
And the call is denied exactly when one of the standalone guards denies it, with that guard's own payload
```

## Scenario: a crashing fail-closed guard inside the PreToolUse dispatcher still denies the call

```gherkin
Given a Bash-matched PreToolUse guard that the upstream contract declares fail-closed raises an exception on a payload
When the agent makes a Bash tool call with that payload
Then the dispatcher denies the call with that guard's own fail-closed deny
And every other Bash-matched guard is still evaluated against the call
```

## Scenario: long-running hooks survive a Driver cache update

```gherkin
Given an active session captured hook commands under an older Driver version
And the marketplace advances to a newer Driver version
And the Driver's hook definitions and hook entrypoints match its release tag for the new version
When explicit provisioning or the persistent observer completes reconciliation
Then every declared retained hook path resolves through latest to the validated current payload
And Codex trusts the Driver's hooks, and any trust the Driver re-established was established only after that verification
And the session's Stop hooks execute successfully
```

## Scenario: long-running hooks survive a cache update of any covered plugin

```gherkin
Given an active Codex session captured hook commands under an older version of a covered plugin that is not the Driver
And that plugin declares its hooks only in its default hooks/hooks.json, behind a shell conditional
And the marketplace advances that plugin to a newer version, deleting the older version directory
And that plugin's hook definitions and hook entrypoints match its release tag for the new version
When the persistent observer completes reconciliation
Then every retained hook path of that plugin resolves through latest to its validated current payload
And Codex trusts that plugin's hooks, and any trust the Driver re-established was established only after that verification
And the session's next turn ends with no hook failure
```

## Scenario: an already-open session keeps running its hooks after a covered plugin's installed content changes but its hooks do not

```gherkin
Given an already-open Codex session captured hook commands of a covered plugin
And Codex trusted that plugin's hooks
And the plugin's installed payload then changes, through a new release or through Codex re-materializing the same version, while every hook definition and hook entrypoint stays byte-identical to the plugin's release tag for the installed version
And Codex withdraws its trust in that plugin's hooks
When explicit provisioning or the persistent observer completes reconciliation
Then each retained hook path of that plugin resolves through latest to the validated current payload
And Codex trusts that plugin's hooks again, re-established only after the hook definitions and entrypoints were verified against the plugin's release tag
And the already-open session's next turn runs those hooks with no hook failure and no trust prompt
And where that plugin ships a PreToolUse safety guard, that guard denies a forbidden command in that session again rather than failing open
And Codex's hook-trust bypass was not used and no hook was disabled
```

## Scenario: a covered plugin whose hook trust cannot be safely re-established is reported, not trusted

```gherkin
Given a covered plugin whose hook trust cannot be verified, because its current payload declares a hook definition or hook entrypoint that differs from the plugin's release tag for the installed version, because no release tag corresponding to the installed version can be identified, or because the host's Codex trust records are in a format the Driver does not recognize
When explicit provisioning or the persistent observer reconciles that plugin
Then the Driver establishes no Codex trust for that plugin's hooks and writes no Codex trust state for them
And the failure is reported as a provisioning or observer failure naming the plugin and each affected hook
And ensure-codex-plugins does not report that plugin healthy
And where Codex exposes a setting that refuses tool execution while a configured hook is untrusted, that setting is enabled, so no tool runs with that plugin's guards silently off
And whenever the host does not fail closed, the plugin is reported unhealthy and the report states that Codex will run tools without that plugin's guards until trust is re-established
And Codex's hook-trust bypass is neither used nor recommended
And every other covered plugin is still reconciled
```

## Scenario: a delegating host's push gates on the remote executor and refuses on no verdict

Given this repository's version-controlled configuration opts it in to delegating its pre-push gate

And the pushing host holds the credential to submit to the remote executor

When a git push of a new tree runs the pre-push gate

Then the pre-push path MUST run the delegation client instead of running `just check` on the pushing host

And the push MUST complete only on a passing verdict from the executor

And the push MUST be refused when the executor returns no verdict
