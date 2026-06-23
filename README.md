# livespec-driver-codex

The **Codex Driver** for [livespec](https://github.com/thewoolleyman/livespec)
— the Codex-runtime analog of `livespec-driver-claude`, under
livespec's contract + reference implementations architecture (per
livespec `SPECIFICATION/spec.md` §"Contract + reference
implementations architecture").

A **Driver** is the thin, agent-runtime-specific wrapper through which
a human drives the spec lifecycle interactively. This repo ships ONLY
the thin Codex SKILL.md bindings for the eight spec-side operations.
Everything substantive stays in livespec core:

| Artifact | Ships with |
|---|---|
| Harness-neutral driving prose (`prose/<name>.md`) | livespec core |
| Reference spec-side CLIs (`scripts/bin/<name>.py`) | livespec core |
| JSON schemas, templates | livespec core |
| Thin `/livespec:*` Codex bindings | **this repo** |

The Driver binds core's prose and config-named CLIs only. It has ZERO
dependencies on any orchestrator (the load-bearing Driver ↔
orchestrator zero-dependency invariant).

## Layout

A Codex plugin cannot live at `source.path: "."`, so the plugin sits
in the `livespec/` subdir and the marketplace catalog at the repo root
(`.agents/plugins/marketplace.json`) points at it:

```
.agents/plugins/marketplace.json   # marketplace: livespec-driver-codex
livespec/                          # the plugin (name: livespec)
  .codex-plugin/plugin.json
  skills/<op>/SKILL.md             # ×8
  hooks/hooks.json
  hooks/livespec_footgun_guard.py
```

## Install

Both plugins are required — core carries the prose and CLIs, this
Driver carries the `/livespec:*` commands:

```
codex plugin marketplace add thewoolleyman/livespec
codex plugin add livespec@livespec
codex plugin marketplace add thewoolleyman/livespec-driver-codex
codex plugin add livespec@livespec-driver-codex
```

The eight skills become available with the `livespec:` namespace
prefix (the Driver plugin is deliberately NAMED `livespec` so the
established `/livespec:*` surface is preserved):

- `seed` — author the initial natural-language spec
- `propose-change` — file a proposed change against the spec
- `critique` — surface issues in the spec
- `revise` — accept or reject pending proposed changes
- `doctor` — run static + LLM-driven validation
- `prune-history` — collapse old `history/vNNN/` entries
- `next` — rank the next spec-side action
- `help` — overview + routing to the right sub-command

## How the bindings find livespec core

Each SKILL.md resolves the livespec core plugin root (`<core-root>`)
at runtime, in order:

1. the `LIVESPEC_CORE_PLUGIN_ROOT` environment variable (explicit
   override);
2. `<project-root>/.claude-plugin/prose/` when the governed project
   IS the livespec core repo (`--plugin-dir .` dev mode /
   dogfooding);
3. the installed `livespec@livespec` plugin's `source.path`, read
   from `codex plugin list --json -m livespec`.

It then reads `<core-root>/prose/<name>.md` (the harness-neutral
driving prose) and dispatches the operation's CLI as named in the
governed project's `.livespec.jsonc` `spec_clis` section (argv-form,
pre-populated with core's reference defaults, individually
overridable per livespec `contracts.md` §"Spec-side CLI contract").

## Footgun guard

The plugin ships a fail-open Codex PreToolUse hook
(`livespec/hooks/livespec_footgun_guard.py`) that refuses
`--no-verify` on commit/push, `LEFTHOOK=0/false`, `core.bare=true`,
and shell edits that would write at a livespec primary checkout. It
always exits 0 and fails OPEN on any uncertainty, so it never blocks
legitimate work; the family commit-refuse hook + branch protection are
the real backstops.

## Development

Family-standard toolchain: `mise` pins the non-Python binaries (`uv`,
`just`, `lefthook`); `uv` manages Python and the dev deps. `just check`
is the full enforcement aggregate — it runs `check-plugin-structure`
(the Codex-layout structural gate), `check-lint`, `check-format`,
`check-hooks` (the footgun-guard unit tests), `check-e2e-cli` (the CLI
end-to-end harness, mock tier), and `check-heading-coverage`. The same
suite runs in lefthook (pre-commit/pre-push) and in the per-target
matrix CI (`.github/workflows/ci.yml`).

The `SPECIFICATION/` tree dogfoods livespec: the Driver's own seam
(binding shape, core-root resolution, the Codex plugin/marketplace
manifest layout, and the footgun-guard hook) is the live spec, evolved
through `livespec:seed` / `propose-change` / `revise` / `doctor` /
`prune-history` / `critique`.

## Status

The functional Driver core plus the full family-infra (toolchain, the
structural gate, the test suite, the dogfooded `SPECIFICATION/`, and CI)
are in place; `just check` passes. The per-repo beads tenant connection
block (and the committed `.beads/config.yaml`) remain deferred to a
later family-infra phase (see `.livespec.jsonc`).
