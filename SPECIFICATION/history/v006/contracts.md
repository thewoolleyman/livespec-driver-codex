# contracts.md — livespec-driver-codex

The contracts in this file are the Driver-owned seam: the shapes and
disciplines that must hold at the boundary between Codex, this Driver
plugin, and livespec core. Each one is mechanically enforced by
`dev-tooling/check_plugin_structure.py` unless noted otherwise. Where a
contract has an upstream owner, this file cites it rather than restating
it.

## Plugin manifest and marketplace

A Codex plugin cannot live at `source.path: "."` — the plugin must sit
in a subdir. So the Driver plugin is declared by
`livespec/.codex-plugin/plugin.json` (the plugin lives in the `livespec/`
subdir), and the marketplace catalog lives at the repo root under
`.agents/plugins/marketplace.json` and points at that subdir. The
following invariants hold (enforced by `check_plugin_structure`):

- `.agents/plugins/marketplace.json` and `livespec/.codex-plugin/plugin.json`
  MUST parse as JSON.
- The plugin `name` MUST be `livespec` — preserving the established
  `livespec:*` command surface. The marketplace `name` MUST be
  `livespec-driver-codex`.
- `plugin.json` MUST carry a non-empty `version`, `skills` equal to
  `./skills/`, and `hooks` equal to `./hooks/hooks.json`.
- `marketplace.json` MUST list exactly ONE plugin entry. That entry's
  `name` MUST be `livespec`, its `source` MUST be
  `{"source": "local", "path": "./livespec"}`, and its `description` MUST
  duplicate `plugin.json`'s `description` verbatim. `plugin.json` is the
  source of truth for the description.

This is the Driver-local, Codex-shaped realization of livespec core's
`contracts.md`, which owns the cross-cutting rule
that plugin and marketplace share the value `livespec` by deliberate
choice (renaming either flows through a core propose-change cycle). The
subdir layout (`livespec/` plugin dir, `.codex-plugin/plugin.json`,
repo-root `.agents/plugins/marketplace.json`) is the Codex-runtime
deviation from the Claude layout and is Driver-owned.

## Skill-binding set

The bundle MUST ship exactly the eight bindings, one per spec-side
operation: `seed`, `propose-change`, `critique`, `revise`, `doctor`,
`prune-history`, `next`, `help`. For each:

- a directory `livespec/skills/<name>/` MUST exist;
- it MUST contain a `SKILL.md`;
- that `SKILL.md` MUST open with a `---`-fenced frontmatter block whose
  `name` equals `<name>` and whose `description` is non-empty;
- the frontmatter MUST NOT carry an `allowed-tools` key (Codex skills
  have no allowed-tools surface).

No extra skill directories may exist, and none of the eight may be
missing. The operation *set* is a core contract (`livespec/SPECIFICATION/spec.md`); this contract governs the Driver-local
binding directories that realize it.

Each binding body MUST carry the Codex core-resolution invocation
`codex plugin list --json -m livespec` (§"Core-root resolution"), and
MUST NOT carry any Claude-runtime marker: a `/livespec:` slash-command
form, the Claude `installed_plugins.json` resolution artifact, the
phrase `Claude Code Driver`, or the sibling repo name
`livespec-driver-claude`. These body invariants are enforced by
`check_plugin_structure`.

## Core-root resolution

Every binding resolves `<core-root>` — the livespec core plugin root from
which it reads operation prose and dispatches the spec-side CLIs — by the
following ordered algorithm, surfaced to shell as `$LIVESPEC_CORE_ROOT`:

1. the `LIVESPEC_CORE_PLUGIN_ROOT` environment variable, when set
   (explicit operator override);
2. else `<project-root>/.claude-plugin/` when the governed project IS the
   livespec core repo — the `--plugin-dir .` dev / dogfooding path (core
   ships its prose under `.claude-plugin/prose/` regardless of which
   Driver runtime is consuming it);
3. else the installed `livespec@livespec` plugin's `source.path`, read
   from `codex plugin list --json -m livespec`.

This resolution order is load-bearing and Driver-owned: livespec core is
agnostic to how a Driver finds it. A binding MUST NOT hardcode a core
path and MUST NOT assume a single installation shape. Resolution
fail-modes (no override set, governed project is not core, no installed
cache) fall through the ordered list; a binding that exhausts the list
without resolving `<core-root>` MUST surface a clear diagnostic (the
`codex plugin marketplace add` / `codex plugin add` install instructions)
rather than dispatch against an unresolved path.

## Fenced-invocation discipline

Within any `SKILL.md`, every fenced command line that invokes a core
wrapper CLI (a `bin/<name>.py` invocation) MUST resolve the wrapper
through `$LIVESPEC_CORE_ROOT`, and MUST NOT:

- use `uv run` (the installer flattens the plugin and omits the `uv`
  project files; the wrappers run under bare `python3`);
- use a literal `.claude-plugin/scripts` path (the binding must resolve
  the script through the core-root variable, not a fixed relative path);
- use the Driver's own plugin-root placeholder (`CLAUDE_PLUGIN_ROOT`),
  which resolves to the DRIVER root — the Driver bundle carries no
  `scripts/` tree, so this would resolve to a path with no wrappers.

The blessed form is `python3 "$LIVESPEC_CORE_ROOT/scripts/bin/<name>.py" …`.
`check_plugin_structure` walks every `SKILL.md`, tracks fenced regions,
and emits one violation per offending invocation line.

## Hook bundle

The Driver SHIPS a Codex hook bundle at `livespec/hooks/`: a `hooks.json`
registration plus four fail-open scripts — the `livespec_footgun_guard.py`
PreToolUse guard, the `block_auto_memory.py` PreToolUse guard, the
`no_shadow_ledger.py` Stop hook, and the `codex_background_memory_audit.py`
Stop hook. Codex consumes
the Claude hook I/O formats, so the guard reads
`{"tool_name": "Bash", "tool_input": {"command": "..."}}` on stdin and
emits a `hookSpecificOutput.permissionDecision: "deny"` payload to
deny a call (empty stdout + exit 0 lets it through), and the Stop hook
reads `{"transcript_path": "...", "stop_hook_active": ...}` on stdin and
emits a `{"systemMessage": "..."}` WARNING (empty stdout passes silently).
Each script is invoked by the runtime as
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<script>.py"` — here the Driver's
own plugin-root placeholder IS correct, since the scripts are Driver-owned
and live in the Driver bundle, and the substitution works for Codex hooks.
`hooks.json` MUST NOT carry a top-level `description` key (Codex's hooks
parser rejects it). The bundle's *existence and wiring* are this repo's
contract; each hook's *behavioral disciplines and postures* (the fail-open
requirement, deny-vs-warn, the gating predicates) are owned upstream by
`livespec/SPECIFICATION/contracts.md`, which this
repo realizes. The script implementations and their unit tests live in
THIS repo (`tests/hooks/`).

The bundle carries FOUR hooks.

A **PreToolUse** guard on `Bash` that DENIES only patterns that are never
legitimate in the livespec family, each with an actionable message naming
the correct alternative:

- (a) `git … commit/push … --no-verify`;
- (b) a leading `LEFTHOOK=0|false` env-assignment (the `--no-verify`
  equivalent);
- (c) `git config core.bare <true>` (the SET form — both `core.bare true`
  and `core.bare=true`; `--get`/`--unset`/`--list` reads pass);
- (d) a shell edit (redirect / `tee` / `sed -i`) that would WRITE FILES
  at a livespec PRIMARY checkout (a git repo whose
  `git config --get livespec.primaryPath` equals its own worktree root);
- (e) Codex tmux fleet-kill hazards in the shared host socket namespace:
  `tmux kill-server` without explicit non-default `-L`/`-S` scoping,
  `tmux -L default kill-server`, fleet/default `-S` socket targets, and
  `pkill`/`killall` targeting `tmux`. `TMUX_TMPDIR` is NOT trusted as a
  scoping control, and shell wrappers such as `sh -c` / `bash -lc` are
  inspected recursively.

Detection is token/segment based (the EXECUTED leading command of a
shell segment), so the dangerous strings appearing as DATA (an `echo`, a
`git config --get` read, a here-doc body, a commit message) are NOT
denied. The guard ALWAYS exits 0. The git/primary-checkout checks fail
OPEN on parse/tokenize error — a guard bug must never block legitimate
work; the family commit-refuse hook and branch protection are the real
backstops, and this guard is only a fast early warning. The tmux
fleet-kill check is the exception: a command containing a tmux kill
hazard that cannot parse safely is DENIED fail-closed, because Codex
agents share the host tmux socket namespace and an unscoped default
socket kill can terminate unrelated agents.

A **PreToolUse** guard on `Write` and `Edit` (`block_auto_memory.py`) that
intercepts writes to the Codex local-memory store (`~/.codex/memories/`)
in a livespec-governed project (one whose `.livespec.jsonc` carries a
non-empty `implementation.plugin`). The deny reason routes the would-be
write BY INTENT — NOT silently dropping it — naming four durable
destinations: trackable work to the active impl-plugin's
`/<plugin>:capture-work-item` skill (namespace resolved dynamically from
`implementation.plugin`, NEVER hardcoded); a spec-level rule or behavior
to `/livespec:propose-change`; durable agent guidance / a learned
preference / a convention to `AGENTS.md` or a focused instruction file
`AGENTS.md` references (loaded progressively/conditionally); and only
genuinely session-only, throwaway notes may be dropped. This is the
Codex-runtime sibling of the Claude Driver's `block-auto-memory` guard;
it covers the manual-write path only — KNOWN LIMITATION: Codex's
background-generated primary memories are outside the pre_tool_use hook
lifecycle, so this guard cannot intercept them. Governance detection:
`CLAUDE_PROJECT_DIR` env var is tried first, then cwd-walk looking for
`.livespec.jsonc`. Fail-open: any exception, non-match, or missing
governance is a silent pass-through, exit 0; the hook denies ONLY when
it POSITIVELY identifies a governed project and a write into the memory
store.

A **Stop** hook (`no_shadow_ledger.py`) that WARNS — never blocks — when
the last assistant turn persisted a PLANNING ARTIFACT (a `*handoff*.md`,
or any `.md` under a `plan/` or `prompts/` directory) whose written
content embeds a markdown checkbox task queue (`[ ]`/`[x]` list items) at
or above a mechanical threshold, instead of deriving status from the
work-item ledger. It realizes the livespec core
`non-functional-requirements.md` "No shadow ledger" rule, per the core
`contracts.md` (v140) contract. WARN-ONLY: it emits a `{"systemMessage": ...}` advisory on
stdout and NEVER a blocking `decision`, NEVER exits non-zero, and NEVER
auto-edits; it fails OPEN (silent exit 0) on any malformed stdin,
`stop_hook_active` re-entry, or missing/unreadable transcript. The body
is BYTE-IDENTICAL to the claude Driver's copy (single-sourced neutral
body); each Driver's `hooks.json` Stop entry is the thin per-runtime
adapter that invokes it, and Codex consumes the Claude Stop hook I/O
shape. The mechanical detection internals (the planning-artifact path
predicate, the checkbox threshold, the persisting-tool set) are Driver
implementation detail and MAY be tuned without a core spec cycle, per the
upstream contract, provided the WARN-only Stop posture holds.

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

Trust model: Codex prompts once to trust a plugin's hooks in interactive
sessions; a headless invocation needs `--dangerously-bypass-hook-trust`
to run the guard without the trust prompt. The trust posture is a Codex
runtime concern, not a Driver contract.

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

## Versioning

`plugin.json.version` is the single source of truth for the shipped
Driver plugin's version and is auto-managed by `release-please` from
per-commit Conventional Commits. `marketplace.json` MUST NOT carry a
`version` field. This mirrors livespec core's `contracts.md`; the Driver follows the same release mechanism for
its own plugin artifact.
