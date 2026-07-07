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
