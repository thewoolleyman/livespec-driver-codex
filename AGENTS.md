# livespec-driver-codex — repo orientation

This repo is the **Codex Driver** for the livespec family: the thin,
agent-runtime-specific SKILL.md bindings through which a human drives
the livespec spec lifecycle interactively under Codex (per livespec
`SPECIFICATION/spec.md` §"Contract + reference implementations
architecture"). It is the Codex-runtime analog of
`livespec-driver-claude`, and it is deliberately small. Everything
substantive — the harness-neutral driving prose, the reference
spec-side CLIs, the schemas, the templates — ships with livespec core
(`thewoolleyman/livespec`); this repo only binds that material to the
Codex runtime.

## Layout

A Codex plugin cannot live at `source.path: "."`; the plugin must sit
in a subdir. So the marketplace catalog lives at the repo root under
`.agents/plugins/` and points at the `livespec/` subdir, which is the
plugin itself.

| Path | Purpose |
|---|---|
| `.agents/plugins/marketplace.json` | Marketplace catalog (`livespec-driver-codex`) listing the single `livespec` Driver plugin, sourced from the `./livespec` subdir. |
| `livespec/.codex-plugin/plugin.json` | Plugin manifest. The plugin is NAMED `livespec` (not `livespec-driver-codex`) so the established `/livespec:*` command surface is preserved. |
| `livespec/skills/<name>/SKILL.md` | The eight thin Codex bindings: seed, propose-change, critique, revise, doctor, prune-history, next, help. |
| `livespec/hooks/` | Plugin-shipped Codex hooks: `hooks.json` declares the events; `livespec_footgun_guard.py` is a fail-open PreToolUse guard resolved via the Driver's plugin root (this IS Driver-owned runtime surface, unlike prose/CLIs). |
| `.livespec.jsonc` | Project-local livespec config: `template`, `spec_root`, active impl-plugin, and the Driver `compat` block. (The beads tenant connection block is DEFERRED to a later family-infra phase.) |
| `dev-tooling/` | `check_plugin_structure.py` (the Codex-layout structural gate) plus the family-standard `git-hook-wrapper.sh` scaffold. |
| `tests/` | `tests/hooks/` (footgun-guard subprocess unit tests) and `tests/e2e-cli/` (the CLI end-to-end harness consumer: mock-tier discovery + fail-closed coverage gate + static binding assertions). |
| `SPECIFICATION/` | The dogfooded live spec for the Driver seam (`spec.md`, `contracts.md`, `constraints.md`, `non-functional-requirements.md`, `scenarios.md`, `history/v001/`). |
| `justfile`, `lefthook.yml`, `pyproject.toml` | Family-standard task runner, git-hook config, and dev-tooling pins. |
| `.github/` | Per-target matrix CI (`workflows/ci.yml`) + the closed-loop Honeycomb telemetry export script. |
| `.mise.toml`, `.python-version`, `.gitignore` | Family-standard toolchain configuration, scaled to this repo's content. |

The family-infra (justfile, lefthook, pyproject, dev-tooling, tests,
dogfooded `SPECIFICATION/`, CI) is present and `just check` passes. The
per-repo beads tenant connection block (and the committed
`.beads/config.yaml`) remain DEFERRED to a later family-infra phase, as
recorded in `.livespec.jsonc`.

## The one design rule that matters here

Each SKILL.md is self-contained and follows the same three-part shape:

1. **Resolve `<core-root>`** — the livespec CORE plugin root. The
   Driver's own plugin root carries no `prose/` and no `scripts/`;
   the bindings resolve core via (a) the `LIVESPEC_CORE_PLUGIN_ROOT`
   env override, (b) `<project-root>/.claude-plugin/prose/` when the
   governed project IS the livespec core repo (dev mode /
   dogfooding), then (c) the installed `livespec@livespec` plugin's
   `source.path`, read from `codex plugin list --json -m livespec`.
2. **Read the prose** — `<core-root>/prose/<name>.md` is the complete
   harness-neutral driving prose; the binding executes it.
3. **Dispatch the config-named CLI** — the governed project's
   `.livespec.jsonc` `spec_clis.<key>` argv (or core's reference
   default `python3 <core-root>/scripts/bin/<name>.py`), expanding
   the plugin-root substitution token in config values to
   `<core-root>` per livespec `contracts.md` §"Spec-side CLI
   contract". (The `help` binding is narration-only and has no CLI
   dispatch.)

Edit livespec core's `prose/<name>.md` for BEHAVIOR changes; edit the
SKILL.md files here only for Codex-runtime mechanics. Never vendor
prose or CLI logic into this repo.

Invocation-form rule for fenced commands in SKILL.md files: use
`python3 "$LIVESPEC_CORE_ROOT/scripts/bin/<name>.py"`, never `uv run`,
never a literal `.claude-plugin/scripts` path, and never the Driver's
own plugin-root placeholder for core paths.

## Relationship to the family

- `livespec` — core: contract, prose, reference CLIs, templates.
- `livespec-driver-claude` — the Claude Code Driver (template this
  repo mirrors).
- `livespec-driver-codex` (this repo) — the Codex Driver.
- `livespec-impl-*` / `livespec-orchestrator-*` — orchestrator
  plugins (work-item stores, gap and drift capture). The Driver has
  ZERO dependencies on them, and they have ZERO dependencies on the
  Driver (load-bearing invariant).

## Codex dogfooding (OpenAI Codex CLI/TUI)

This repo IS the Codex Driver — the `/livespec:*` operation surface
under OpenAI Codex CLI/TUI. To dogfood the eight spec-side operations
from Codex (against this repo's own dogfooded `SPECIFICATION/`, or any
governed project), install TWO plugins host-wide: livespec CORE (the
artifact carrier that ships the harness-neutral prose and reference
wrappers, no skills of its own) and THIS repo (the Codex Driver, which
supplies the operation surface over core's prose). Unlike the Claude
path — where plugins are enabled PER PROJECT via a committed
`.claude/settings.json` — Codex plugin enablement is **HOST-WIDE**:
each registration persists in `~/.codex/config.toml` and applies to
every project on the host. Codex offers no project-scoped plugin
enablement, so there is no committed-settings analogue for the Codex
path.

```bash
# livespec CORE (spec-side prose + wrappers; no skills of its own):
codex plugin marketplace add thewoolleyman/livespec
codex plugin add livespec@livespec

# This repo — the Codex Driver (supplies the /livespec:* operation surface):
codex plugin marketplace add thewoolleyman/livespec-driver-codex
codex plugin add livespec@livespec-driver-codex
```

Both registrations persist HOST-WIDE in `~/.codex/config.toml` (a
`[marketplaces.<name>]` entry plus a `[plugins."<plugin>@<marketplace>"]
enabled = true` entry). The Driver plugin is deliberately NAMED
`livespec` (not `livespec-driver-codex`) so the established
`/livespec:*` command surface is preserved across both marketplaces.

Once installed, the eight operations (`seed`, `propose-change`,
`critique`, `revise`, `doctor`, `prune-history`, `help`, `next`) are
driven from Codex via `codex exec` and NAME-selected as `livespec:<op>`
(e.g. `livespec:next`) rather than as `/`-prefixed slash commands.
`codex exec` resolves this Driver's binding, which reads CORE's prose
(`<core-root>/prose/<name>.md`) and dispatches the spec-side wrapper
named in the governed project's `.livespec.jsonc` `spec_clis` section —
exactly the runtime resolution described under "How the bindings find
livespec core" in `README.md`. No `AGENTS.md` skill→prose mapping is
required; the distributed Driver resolves the prose itself. See
`livespec/SPECIFICATION/contracts.md` §"Plugin distribution" and
`livespec/SPECIFICATION/non-functional-requirements.md` §"Codex
dogfooding contracts" for the authoritative install and resolution
contracts.

Daily-dogfooding note: edit livespec core's `prose/<name>.md` for
BEHAVIOR changes — those flow to BOTH runtimes — and edit the SKILL.md
bindings HERE only for Codex-runtime mechanics (per "The one design
rule that matters here" above). For local development against an
in-checkout core, set `LIVESPEC_CORE_PLUGIN_ROOT` to the core
checkout's `.claude-plugin/`, or run inside the core repo itself (the
Driver auto-resolves `<project-root>/.claude-plugin/prose/` when the
governed project IS the core repo). A temporary local Codex marketplace
registration used for testing MUST be removed afterward unless you
explicitly ask to keep it.
