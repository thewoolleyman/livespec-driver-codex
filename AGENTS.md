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
| `livespec/hooks/` | Plugin-shipped Codex hooks: `hooks.json` declares the events; `livespec_footgun_guard.py` is a fail-open PreToolUse guard resolved via the Driver's plugin root (this IS Driver-owned runtime surface, unlike prose/CLIs). Every hook here MUST be self-contained — see "Shipped hooks are self-contained" below. |
| `.livespec.jsonc` | Project-local livespec config: `template`, `spec_root`, active impl-plugin, the Driver `compat` block, and the per-repo beads tenant connection block (mirroring the committed `.beads/config.yaml`). |
| `dev-tooling/` | The family-standard git-hook scaffolds. The structural gate is no longer vendored here — `check-plugin-structure` consumes the profile-auto-detecting check from the shared `livespec-dev-tooling` package (`python -m livespec_dev_tooling.driver_checks.plugin_structure`). The commit-refuse hook is likewise no longer a vendored `git-hook-wrapper.sh` scaffold here — `just bootstrap` installs the canonical structural hook from the same package (`python -m livespec_dev_tooling.install_commit_refuse_hooks`, the SINGLE source of the hook body; both pinned in `pyproject.toml`). |
| `tests/` | `tests/hooks/` (footgun-guard subprocess unit tests) and `tests/e2e-cli/` (the CLI end-to-end harness consumer: mock-tier discovery + fail-closed coverage gate + static binding assertions + live Codex `/skills` picker acceptance). |
| `SPECIFICATION/` | The dogfooded live spec for the Driver seam (`spec.md`, `contracts.md`, `constraints.md`, `non-functional-requirements.md`, `scenarios.md`, `history/v001/`). |
| `justfile`, `lefthook.yml`, `pyproject.toml` | Family-standard task runner, git-hook config, and dev-tooling pins. |
| `.github/` | Per-target matrix CI (`workflows/ci.yml`) + the closed-loop Honeycomb telemetry export script. |
| `.mise.toml`, `.python-version`, `.gitignore` | Family-standard toolchain configuration, scaled to this repo's content. |

The family-infra (justfile, lefthook, pyproject, dev-tooling, tests,
dogfooded `SPECIFICATION/`, CI) is present and `just check` passes. The
per-repo beads tenant is WIRED and CONNECTED: the committed
`.beads/config.yaml` and the `.livespec.jsonc` connection block describe
the server-mode tenant (user/db `livespec-driver-codex`, TCP-only over
`127.0.0.1:3307`, no socket key; the tenant password is supplied via
`BEADS_DOLT_PASSWORD` at bd-call time and never committed).

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

## Shipped hooks are self-contained

The plugin's packaged root is `./livespec` (`.agents/plugins/marketplace.json`
`plugins[0].source.path`), so Codex copies `livespec/` — and **nothing above
it** — into its install cache at `<cache>/livespec/<version>/hooks/<file>.py`,
then runs each hook with a bare `python3`: no venv, no third-party packages.

Two rules follow, and both are load-bearing for safety:

1. **Every import a shipped hook makes must resolve inside `livespec/`** — the
   stdlib, or a plain sibling module (`from _footgun_shell import ...`,
   `from _result import ...`), which resolves because Python puts a script's
   own directory on `sys.path`.
2. **No path arithmetic.** Never reconstruct a repo root with
   `Path(__file__).resolve().parents[N]` and insert it on `sys.path`.

Violating either produces a failure mode that looks like success. A module-scope
`ModuleNotFoundError` raises BEFORE `main()`'s fail-open `try`/`except`, so the
process exits non-zero and Codex fails the hook OPEN — the dangerous command
runs unblocked while `codex plugin list` still shows the guard installed and
`${CLAUDE_PLUGIN_ROOT}` still resolves. This actually shipped: five hooks
imported a repo-root `_vendor.returns` shim that is not packaged, and the
footgun guard silently stopped blocking tmux fleet-kills.

The in-repo test suite cannot catch this on its own, because it runs the hooks
from the checkout where the repo root happens to be reachable — which is exactly
why the defect shipped green. `tests/hooks/test_shipped_hooks_install_shape.py`
is the gate that does catch it: it copies ONLY `livespec/` into a mock install
cache, runs each hook there under an interpreter that ignores `PYTHONPATH`, and
asserts real verdicts. Any new shipped hook belongs in that test.

## Relationship to the family

- `livespec` — core: contract, prose, reference CLIs, templates.
- `livespec-driver-claude` — the Claude Code Driver (template this
  repo mirrors).
- `livespec-driver-codex` (this repo) — the Codex Driver.
- `livespec-impl-*` / `livespec-orchestrator-*` — orchestrator
  plugins (work-item stores, gap and drift capture). The Driver has
  ZERO dependencies on them, and they have ZERO dependencies on the
  Driver (load-bearing invariant).

## Repository mutation protocol

Every repo change uses a worktree → PR → merge → cleanup path. Treat
leaving dirty state, committing on the primary checkout, or asking the
user whether to commit as failures of the workflow, not as acceptable
stopping points.

The prohibition is about tracked repository changes and other persistent
primary-checkout edits. The sole operational exception is the gitignored
runtime subtree `<repo-primary>/tmp/overseer/<topic>/`: a supervisor may
create or update runtime state there (for example `.supervisor-state`, wait
channels, watcher logs, and PID files) directly in the primary checkout.
The exception is exact: the path MUST contain a non-empty single `<topic>`
component immediately below `tmp/overseer/`, MUST resolve beneath that topic
directory, and MUST remain ignored by the repository. It does not permit
writes to `tmp/overseer/` itself, sibling `tmp/` paths, tracked files, or any
other primary-checkout path. Every tracked change and every other persistent
write still uses the worktree → PR → merge → cleanup path below.

1. Confirm the primary checkout before editing (a primary checkout's
   git-dir equals its git-common-dir; a secondary worktree's differs —
   the structural test the commit-refuse hook itself uses):

   ```bash
   git -C /data/projects/livespec-driver-codex rev-parse --git-dir --git-common-dir
   git -C /data/projects/livespec-driver-codex status --short --branch
   ```

2. If the change will modify tracked files, create a dedicated worktree
   from the primary checkout's `master` and do all edits there. Every
   worktree lives under the per-user root `~/.worktrees/<repo>/<branch>`
   — NEVER as a peer of the clones under `/data/projects`, and NEVER
   under `.claude/worktrees/` (that path is outside mise's
   `trusted_config_paths`, so `.mise.toml` there is untrusted by
   default and every `mise exec`/`uv`/`just` invocation fails closed
   until `mise trust` is run by hand):

   ```bash
   mise exec -- git -C /data/projects/livespec-driver-codex worktree add -b <branch> "$HOME/.worktrees/livespec-driver-codex/<branch>" master
   ```

   `just bootstrap` registers `~/.worktrees` as one of mise's
   `trusted_config_paths`, so a freshly created worktree's `.mise.toml`
   is auto-trusted and the first `mise exec` inside it never stalls on a
   "config not trusted" prompt.

3. Use `mise exec -- git commit ...` and `mise exec -- git push ...` so
   the mise-managed lefthook hooks actually run. Never pass
   `--no-verify`; if a hook fails, fix the cause or halt with the
   failure.
4. Open a PR, wait for required checks, and merge through the PR using
   the repo's rebase-merge discipline.
5. After merge, refresh `/data/projects/livespec-driver-codex` to
   `origin/master`, remove the feature worktree, delete the local
   branch, and verify the primary checkout is clean on `master`.

Do not leave orphaned worktrees. If a session must stop before cleanup,
record the active worktree path, branch, PR, validation state, and next
action in the plan epic's attributed ledger entries, with any supporting
research preserved under the plan's `research/` directory. For stale
cleanup outside the current branch's own worktree, use the repo's reaper
entry point rather than hand-deleting unfamiliar state:

```bash
just reap-stale-worktrees <repo> --dry-run   # INSPECT — reports, changes nothing
just reap-stale-worktrees                    # ACTS — removes worktrees, deletes branches
```

**The bare form is not a report. It reaps.** It removes every worktree it
classifies stale and deletes those branches, in seconds, with no
confirmation. Reach for `--dry-run` first, always, and NEVER use the bare
form to check whether the recipe works — that is running a destructive
command to see what it does. The two forms sitting side by side is
precisely what makes this easy to get wrong: a documented `--dry-run`
variant makes the family *feel* safe, when it means the other form is the
live one.

The reaper only removes worktrees whose branches it judges stale, so the
usual outcome is harmless — but that is a property of the tool, not of the
invocation, and you cannot know it held until after it has run. Never reap
while a dispatched agent is working in one of that repo's worktrees.

(Adapted from `livespec` core's `AGENTS.md` §"Repository mutation
protocol" — see that repo for the canonical, most up-to-date version.)

## Codex dogfooding (OpenAI Codex CLI/TUI)

This repo IS the Codex Driver — the `/livespec:*` operation surface
under OpenAI Codex CLI/TUI. To dogfood the eight spec-side operations
from Codex (against this repo's own dogfooded `SPECIFICATION/`, or any
governed project) plus the family orchestrator surface, install three
plugins host-wide: livespec CORE (the artifact carrier that ships the
harness-neutral prose and reference wrappers, no skills of its own),
THIS repo (the Codex Driver, which supplies the operation surface over
core's prose), and the selected orchestrator plugin. Unlike the Claude
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

# The selected orchestrator plugin (supplies its own Codex skills):
codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro
codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro
```

These registrations persist HOST-WIDE in `~/.codex/config.toml` (a
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
livespec core" in `README.md`. The orchestrator plugin adds its own
Codex skills (`drive`, `next`, `list-work-items`,
`detect-impl-gaps`, `capture-work-item`, `capture-impl-gaps`,
`capture-spec-drift`, `implement`, `groom`) under its plugin name. No
`AGENTS.md` skill→prose mapping is required; the distributed Drivers
resolve their prose themselves. See `livespec/SPECIFICATION/contracts.md`
§"Plugin distribution" and
`livespec/SPECIFICATION/non-functional-requirements.md` §"Codex dogfooding
contracts" for the authoritative install and resolution contracts.

The Codex TUI picker displays skills differently from the name-selection
form above. In `/skills` → `List skills` (or the `@` picker), search by the
short skill name, for example `drive`; Codex renders the match as
`drive (livespec-orchestrator-beads-fabro)` with kind `Skill`. Do not
expect the picker row to be searchable only as
`livespec-orchestrator-beads-fabro:drive`; that colon-qualified form is
for prompt / `codex exec` name selection and model-visible skill references.

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

## CI runner routing

`CI_RUNNER_LABELS` (a repo variable, never a `.github/workflows/` edit —
`check-no-workflow-edits` forbids that here) routes this repo's gating
`pull_request`/`push` CI matrix. As of 2026-08-17 it points at the ARC k3s
scale set `livespec-driver-codex-k3s` (livespec-s43svm.16's per-repo
real-traffic cutover), proven by this changeset's own required checks. The
podman pool alternative stays configured but idle for this repo. See
`livespec/plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md`
("Real-traffic cutover log") and the `livespec-s43svm.16` ledger comments for
the full cross-repo cutover record.
