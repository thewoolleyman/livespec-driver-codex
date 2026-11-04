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
registration with PreToolUse guards and Stop hooks, including the `livespec_footgun_guard.py`
PreToolUse guard, the `block_auto_memory.py` PreToolUse guard, the
`no_shadow_ledger.py` Stop hook, and the `codex_background_memory_audit.py`
Stop hook, together with the `supervisor_completion_gate.py` Stop gate specified
in §"Supervisor completion gate". Codex consumes
the Claude hook I/O formats, so the guard reads
`{"tool_name": "Bash", "tool_input": {"command": "..."}}` on stdin and
emits a `hookSpecificOutput.permissionDecision: "deny"` payload to
deny a call (empty stdout + exit 0 lets it through), and the warning Stop hooks
read `{"transcript_path": "...", "stop_hook_active": ...}` on stdin and
emits a `{"systemMessage": "..."}` WARNING (empty stdout passes silently).
A guard is **Bash-matched** when any matcher it is registered on is `Bash`.
The runtime MUST start every Bash-matched PreToolUse guard, for a `Bash` call,
through ONE dispatcher entry point,
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_dispatch.py"` registered on
the `Bash` matcher, so one Bash tool call starts one Python process for the
Driver's PreToolUse guards rather than one per guard. A Bash-matched guard
that is also registered on other tools (for example `block_auto_memory.py`
on `Write`, `Edit` and `apply_patch`) keeps its own entry point on those
other matchers. The dispatcher imports each Bash-matched guard module and
evaluates every guard in-process, in its dispatch order, against the same
payload. Each guard runs inside its OWN failure boundary, which discharges
that guard's declared failure posture: when a guard raises or returns a
malformed result, a fail-open guard is treated as an allow for that guard
alone, and a guard (or guard check) the upstream contract declares
fail-closed is treated as that guard's own deny, exactly as its standalone
boundary would emit. Either way the failure MUST NOT suppress, reorder or
alter any other guard's decision. The dispatcher denies the call iff at
least one guard denies it, emitting the
`hookSpecificOutput.permissionDecision: "deny"` payload of the first
denying guard in dispatch order, byte-identical to that guard's payload
when run standalone; otherwise it emits empty stdout and exits 0. The
dispatcher sets no per-guard time budget: a guard that hangs is bounded by
the runtime's hook timeout for the whole dispatcher process. When the
dispatcher itself fails before it has evaluated every guard (it cannot read
the payload, cannot import a guard module, or raises outside any guard's
boundary), it MUST fall back to running each not-yet-evaluated Bash-matched
guard as its own standalone process against the same payload and combine
their decisions by the same deny-iff-any rule, so every guard's declared
failure posture, including a fail-closed check's deny, holds exactly as in
the standalone layout; the fallback MUST NOT deny a call that the
standalone guards would allow. Every
other hook, and each guard script run standalone, is invoked as
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<script>.py"` with unchanged
behaviour. Here the Driver's own plugin-root placeholder IS correct, since
the scripts are Driver-owned and live in the Driver bundle, and the
substitution works for Codex hooks.
`hooks.json` MUST NOT carry a top-level `description` key. The bundle's *existence and wiring* are this repo's
contract; each family-standard hook's *behavioral disciplines and postures* (the fail-open
requirement, deny-vs-warn, the gating predicates) are owned upstream by
`livespec/SPECIFICATION/contracts.md`, which this
repo realizes. The Driver-owned background-memory audit and supervisor
completion gate are governed by this tree. The script implementations and their unit tests live in
THIS repo (`tests/hooks/`).

The following paragraphs specify the family-standard guards and warning hooks;
the Driver-owned supervisor completion gate is specified separately below.

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

A **PreToolUse** guard (`block_auto_memory.py`), registered on `Write`,
`Edit`, `apply_patch` and the shell tool (`Bash`), that refuses every
write into an agent memory directory — the Codex local-memory store
(`~/.codex/memories/`) or the Claude Code auto-memory layout
(`~/.claude/projects/<slug>/memory/*.md`) — in a livespec-governed
project (one whose `.livespec.jsonc` carries a non-empty
`implementation.plugin`). For a file tool it acts on a target path under
either directory; for a shell command it acts only when it POSITIVELY
identifies a write into one, judging each `;`, `&&`, `||` and pipeline
segment and the payload of a `sh -c` / `bash -c` / `env` wrapper, and
recognising at least the write forms livespec core's §"Driver-shipped
hooks" lists (redirection including a here-document, `tee`, `sed -i`,
`perl -i`, `cp`, `mv`, `install`, `ln`, `touch`, `truncate`, `dd of=`, an
inline interpreter write). A command that only reads such a directory,
or removes a note with `rm`, passes. The deny reason is identical on
every route and routes the would-be write BY INTENT — NOT silently
dropping it — naming four durable destinations: trackable work to the
active impl-plugin's `/<plugin>:capture-work-item` skill (namespace
resolved dynamically from `implementation.plugin`, NEVER hardcoded); a
spec-level rule or behavior to `/livespec:propose-change`; durable agent
guidance / a learned preference / a convention to a short discoverable
`AGENTS.md` entry pointing at a `.ai/<topic>.md` file holding the
content, or to `AGENTS.md` alone when the guidance is short; and only
genuinely session-only, throwaway notes may be dropped. This is the
Codex-runtime sibling of the Claude Driver's `block-auto-memory` guard;
it covers the manual-write and shell-write paths only — KNOWN
LIMITATION: Codex's background-generated primary memories are outside
the pre_tool_use hook lifecycle, so this guard cannot intercept them; a
write whose destination path is computed at runtime is likewise a stated
limit. Governance detection: `CLAUDE_PROJECT_DIR` env var is tried
first, then cwd-walk looking for `.livespec.jsonc`. Fail-open: any
exception, non-match, or missing governance is a silent pass-through,
exit 0; the hook denies ONLY when it POSITIVELY identifies a governed
project and a write into an agent memory directory.

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

Trust model: Codex runs a plugin's hooks only while it trusts them, and
it records that trust in the host's Codex configuration. For every
covered plugin, the Driver's own payload included, re-establishing that
trust whenever Codex does not trust the plugin's installed hooks is part
of hook continuity and is governed by §"Codex hook-cache compatibility"
below. The Driver MUST NOT use or recommend Codex's hook-trust bypass
(`--dangerously-bypass-hook-trust`) in any shipped or provisioning
surface as a remedy for untrusted hooks, because the bypass disables a
safety control.

Adding or removing a hook, renaming a hook surface, or changing a hook's
posture requires a propose-change cycle, routed by ownership: for the
family-standard `livespec_footgun_guard.py`, `block_auto_memory.py`, and
`no_shadow_ledger.py` hooks — whose postures are owned upstream — the cycle
runs against the upstream `livespec/SPECIFICATION/contracts.md`; for the
Codex-specific, Driver-owned `codex_background_memory_audit.py` and
`supervisor_completion_gate.py` hooks, the cycle runs against THIS tree. The
mechanical detection internals
(segment tokenization, the primary-checkout probe) are Driver
implementation detail and MAY be tuned without a spec cycle, provided the
postures hold.

### Codex hook-cache compatibility

The reconciler and persistent observer required below are NOT members
of the plugin hook bundle above and are not shipped inside
`livespec/hooks/` — they are `dev-tooling/`-owned executables,
repo-level tooling in the same location and installation path as the
existing `ensure-codex-plugins` provisioner, never copied into or run
from the Codex-managed plugin cache. Their operative copies are
therefore inherently outside the replaceable
`<cache>/<marketplace>/<plugin>/<version>` tree without requiring any
exception to the plugin hook-bundle contract above.

The Driver MUST provide a cache-independent host reconciler and a
persistent update observer. The reconciler and observer cover every
**covered plugin**. A covered plugin is installed in the Codex plugin
cache under a marketplace that has a `[marketplaces.<name>]` entry in
the host's Codex configuration, and its current installed payload
declares at least one hook. A cache directory whose marketplace has no
such entry is not a covered plugin; this is how caches that Codex
manages from its own curated sources are excluded. The covered set MUST
be derived from measured Codex configuration and cache state on every
reconcile, never from a list fixed in code or configuration, so a
plugin that first declares a hook in a later release is covered with no
Driver change. The set includes non-livespec plugins from registered
marketplaces, for example a third-party plugin that ships
`bash`-invoked hooks. Only version-named real directories are version
roots; scratch install directories and non-version-named directories
are neither version roots nor alias targets.

The ordinary `ensure-codex-plugins` provisioner MUST run the reconciler
for every covered plugin after its successful marketplace upgrade and
plugin-install sequence, and MUST verify that the observer is running
and healthy. The observer MUST notice Codex-native startup
auto-upgrades of any covered plugin, wait until that plugin's new cache
payload is complete, then run the same reconciler for that plugin. The
observer MUST NOT busy-wait; its polling or event mechanism is an
implementation detail.

For its own hook-cache discovery step only, the reconciler MUST
discover the actual versioned hook cache from measured cache state and
declared hook commands, and MUST NOT treat `codex plugin list`
`source.path` as a versioned hook location; this prohibition governs
the reconciler's discovery step alone and does not alter §"Core-root
resolution" above, which legitimately reads `source.path` for a
different purpose. Before changing aliases, the reconciler MUST
validate the current payload's hook declarations and every hook
entrypoint they declare, for every hook event, using the bare
interpreter form Codex executes, under the following discovery and
entrypoint rules:

- Hook declarations are discovered from the manifest's `hooks` entry
  and from the payload's default `hooks/hooks.json`. The union of every
  declaration found is validated.
- A hook command's entrypoint is the first path in the command rooted
  at `${CLAUDE_PLUGIN_ROOT}/`, whether the command invokes it through
  `python3`, `bash`, or inside a shell conditional.
- Validation requires each entrypoint to exist inside the payload. An
  entrypoint ending in `.py` MUST additionally compile under the bare
  interpreter form Codex executes.
- A command naming no `${CLAUDE_PLUGIN_ROOT}/` path, and not mentioning
  `CLAUDE_PLUGIN_ROOT` in any form, has no versioned path to preserve.
  It needs no entrypoint validation.
- A command that mentions `CLAUDE_PLUGIN_ROOT` but yields no
  `${CLAUDE_PLUGIN_ROOT}/` entrypoint MUST fail the reconcile for that
  plugin loudly. So MUST an unreadable or malformed hook declaration.
- A command whose `${CLAUDE_PLUGIN_ROOT}/` entrypoint does not exist in
  the payload MUST fail the reconcile for that plugin loudly, naming
  the plugin and the command. Hook continuity MUST NOT be claimed for
  that plugin.
- Structural rules the Driver applies to its OWN `hooks.json`, such as
  rejecting a top-level `description` key, govern the Driver's own
  bundle only. They are not covered-plugin validation.

For the Driver's own payload, that validation also covers
`pretooluse_dispatch.py` as a declared hook and each guard module it
imports. The Driver's own payload remains a covered plugin. The
reconciler MUST maintain a one-hop topology
`old-version -> latest -> current-version`, atomically retarget
`latest` only after validation, preserve complete real version
directories, refuse unsafe or malformed existing links loudly, and
backfill only bounded version names recorded in that plugin's own
version-state record. It MUST be idempotent and MUST report a failed
repair as a provisioning/observer failure rather than claiming hook
continuity.

Hook continuity for a covered plugin requires both path continuity,
which the one-hop alias topology above provides, and trust continuity,
which means Codex trusts that plugin's currently installed hooks.
Codex's trust follows a plugin's installed bytes, not its release: Codex
can withdraw its trust in every hook of a plugin when any part of the
installed payload changes, even when the hook definitions and hook
entrypoints are byte-identical to the previously trusted release, and
even with no version change, for example when Codex re-materializes the
same version and rewrites the plugin's cache metadata. Trust continuity
is a safety invariant: an untrusted hook does not run, so the tool call
an untrusted PreToolUse guard would have guarded proceeds unguarded.
Whenever Codex does not trust a covered plugin's installed hooks, at
least one of the following MUST hold: (a) Codex trust in those hooks is
re-established from release-verified bytes, as the next paragraph
requires; (b) the host fails closed, as the fail-closed fallback
paragraph below requires; (c) where (b) does not hold, the loud
unhealthy report that the fail-closed fallback paragraph requires is
emitted. A host MUST NOT leave Codex sessions running tools with a
covered plugin's guards silently off until a human notices. The
reconciler MUST NOT claim hook continuity for a covered plugin while
either half is missing.

The observer MUST detect, for every covered plugin, both lost Codex
trust and cache content rewritten at an unchanged version, not only
version changes and Codex-native auto-upgrades, and MUST run the
reconciler for that plugin when it detects either. It MUST restore
trust, or emit the report required below, within a bounded latency that
the implementation states and its tests verify. Whenever Codex does not
trust a covered plugin's installed hooks, the reconciler MUST attempt to
re-establish Codex hook trust for those hooks, and it MUST do so only
after verifying the installed payload's declared hook definitions, and
every hook entrypoint they declare, against that plugin's released
artifact: the release tag, in the plugin's source repository, that
corresponds to the installed version. Trust MUST NOT be established on
the strength of the cache contents alone. The verification applies
whether or not a hook definition changed relative to the previously
trusted release, and a hook whose definition changed MUST NOT be trusted
on any other basis. A payload that cannot be verified, because its
released artifact cannot be identified or obtained or because any
declared hook definition or entrypoint differs from that artifact, MUST
NOT be trusted. It MUST be reported as a provisioning or observer
failure naming the plugin and each unverified hook, exactly as a failed
path repair is. In particular, a covered plugin for which no release tag
corresponding to its installed version can be identified, such as a
third-party plugin whose source repository publishes none, MUST be
reported in that way and MUST NEVER be trusted by the Driver. The
reconciler MUST NOT use Codex's hook-trust bypass, and it MUST NOT
disable or remove a hook to clear a trust failure.

Re-establishing trust depends on Codex's hook-trust record format, which
is an external surface that any Codex release may change. The invariant
is trust continuity from release-verified bytes, not any particular
mechanism: whether the Driver re-establishes trust through an interface
Codex provides, by writing Codex's trust records, or by provisioning the
hooks through a Codex mechanism that does not subject them to per-plugin
content-hash trust is an implementation choice. Whatever the mechanism,
every hook whose trust the Driver establishes or provisions MUST be
byte-identical to the release-verified hook definitions and entrypoints.
The reconciler, the observer, and `ensure-codex-plugins` MUST recognize
the format of the host's Codex trust records before reading trust status
from them or writing them. When any of them does not recognize that
format, it MUST NOT write any trust state, MUST treat that plugin's
hooks as untrusted, and MUST fail loudly, as a provisioning or observer
failure naming the plugin. Trust that an operator grants through Codex's
own review interface is not governed by this contract.

Writing the host's Codex configuration. Codex records hook trust in the
host's Codex configuration file, which Codex itself also writes and which
more than one Driver process (the reconciler run by `ensure-codex-plugins`
and the one run by the observer) may write at the same time. Every Driver
write to that file, including trust state and the fail-closed setting that
host provisioning enables, MUST preserve the file's integrity:
(a) the Driver's writers MUST be serialized with one another, including
across separate processes, so that two concurrent writers can never each
read the file and then overwrite what the other wrote; (b) each write MUST
replace the file atomically, so that an interrupted write leaves either the
complete prior file or the complete new file, never a truncated or
partially written one; and (c) each write MUST be computed from the file's
contents as read while serialized, immediately before the replacement, so
that it carries forward every setting it does not intend to change. Codex
does not take part in the Driver's serialization, so clause (c) narrows,
but cannot eliminate, the window in which a concurrent Codex edit could be
overwritten. A writer that cannot meet these conditions within a bounded
wait, which the implementation states and its tests verify, MUST NOT write
and MUST report the failure loudly, as a provisioning or observer failure
naming each plugin whose trust it could not write, exactly as an
unrecognized trust-record format is reported.

`ensure-codex-plugins` and the observer's health report MUST report a
covered plugin whose hooks are installed but not trusted by Codex
loudly, as a failure, naming the plugin and each untrusted hook, and
MUST NOT report that plugin healthy.

Fail-closed fallback. If Codex exposes a setting that refuses tool
execution while a configured hook is untrusted, host provisioning MUST
enable it, and `ensure-codex-plugins` MUST report a host on which it is
not enabled. Whenever the host does not fail closed, because Codex
exposes no such setting or because the setting is not enabled, the
Driver MUST report untrusted covered hooks as unhealthy through
`ensure-codex-plugins` and the observer health check, naming the plugin
and each untrusted hook, and each such report MUST state that Codex will
run tools without that plugin's guards until trust is re-established,
and the Driver MUST NOT describe those guards as active anywhere. In
either case, the Driver and host provisioning MUST NOT use or recommend
Codex's hook-trust bypass (`--dangerously-bypass-hook-trust`, or its
configuration key `bypass_hook_trust`).

Each covered plugin's durable version-state record and observer status
record MUST be keyed by the plugin's marketplace and plugin name. A
health report for one plugin MUST NOT be satisfied by another
plugin's, or another observer instance's, status record. A reconcile
failure for one covered plugin MUST NOT prevent reconciliation of the
others; it MUST be reported as a provisioning or observer failure
naming that plugin.

The Driver MUST ship a service-supervisor definition for the observer on
each supported platform: on Linux a systemd user unit, and on macOS a
launchd user LaunchAgent, shipped beside the systemd unit. Each
definition supervises one observer that reconciles every covered plugin,
and neither names a marketplace or a plugin. With it, host provisioning
can keep the observer running without any Codex or Claude session
starting it: on Linux across host reboots, and on macOS from each
graphical (GUI) login session onward, across reboots and logout/login.
The macOS definition MUST resolve the observer's Python interpreter
correctly on both Apple Silicon and Intel Macs; it MUST NOT depend on an
interpreter location that exists on only one of them.

`ensure-codex-plugins` checks supervision; it does not take supervision
over. It MUST report an observer whose process is not running under the
platform's installed supervisor definition by exiting non-zero and
naming the hook-cache observer, including when no definition is
installed on a platform that has a supported supervisor, and it MUST do
so even while an observer process that the supervisor did not start is
alive. Where the platform has no supported supervisor, it MUST say so
rather than report the observer as supervised. While the supervisor's
observer is running, `ensure-codex-plugins` MUST NOT signal that
process, including when that observer's status record reports a
reconcile error. When that error is the reconcile result reported for
the plugin under the newest-result rule below, it reports that error
instead, as a provisioning or observer failure naming the plugin, and
exits non-zero. `ensure-codex-plugins` MUST NOT start an observer
process, on any platform, whether or not the supervisor's observer is
running; starting the observer is the supervisor's job. It MUST NOT
signal any observer process; where it finds a live observer not running
under the installed supervisor definition, it reports it rather than
terminating it.

Each observer status record for a covered plugin MUST carry the time its
reconcile completed, comparable with the completion time of a reconcile
that `ensure-codex-plugins` runs; when the two times are equal, the
observer's status record counts as the newer. For each covered plugin,
the reconcile result that `ensure-codex-plugins` reports is the newer of
its own reconcile of that plugin in the current run and the observer's
status record for that plugin. An observer status record that reports a
reconcile error and is older than a reconcile of that plugin that
`ensure-codex-plugins` completed without error in the current run MUST
NOT fail provisioning for that plugin, and, provided the observer has
completed at least one reconcile of that plugin, that newer reconcile
satisfies the per-plugin health rule's requirement of a completed
reconcile that reported no error. An observer that has completed no
reconcile of that plugin is still reported unhealthy for it. An observer
status record that reports a reconcile error and is newer than that
reconcile MUST be reported as a provisioning or observer failure naming
the plugin, with a non-zero exit. Apart from that requirement, this rule
decides only which reconcile result is reported; an observer error
superseded by a newer reconcile in this way is not a reconcile failure
for the purposes of any other rule in this section, while every other
rule in this section that reports the plugin unhealthy, including the
trust-continuity and fail-closed rules, still applies.

Observer health is reported per covered plugin. An observer that has
started but has not completed its first reconcile of a covered plugin
MUST be reported unhealthy for that plugin, and MUST NOT be reported
healthy for that plugin until that plugin's own status record carries a
completed reconcile that reported no error, except as the newest-result
rule above provides; a status record written before that first
reconcile, such as a startup heartbeat, MUST NOT satisfy the health
report. This is a necessary condition for health, not a sufficient one:
any other rule in this section that reports the plugin unhealthy still
applies. This holds on every platform.

Installing a supervisor definition on a host, and on Linux enabling
user-session lingering so that the unit runs with no login session, are
the host-provisioning automation's responsibility, not the Driver
provisioner's: neither `ensure-codex-plugins` nor a plugin install
installs, loads, or replaces a supervisor definition as a side effect.
Where no provisioning automation exists for a host, an operator-run
installation of the shipped definition is that host's provisioning step;
a definition generated or hand-written for that host is not.

## Supervisor completion gate

The Driver MUST ship `supervisor_completion_gate.py` as a self-contained Codex
Stop hook. It MUST emit a Codex-compatible `{"decision":"block","reason":...}`
response when continuation is required, and otherwise emit empty stdout, always
exiting zero. Completion evidence MUST come from structured supervisor state
and independently checked wake-producer evidence, never assistant final-response
text or pane text. This is Driver-owned runtime behavior.

The hook MUST determine the current session's supervision topic from explicit
runtime context (`supervisor_topic`, or the compatibility alias `topic`). The
canonical field takes precedence whenever present, including when blank; the
alias is consulted only when the canonical field is absent. A named supervised
session MUST deliver its topic through Driver session-scoped context even when
the native Stop input omits these extension fields. Repository marker discovery
MUST NOT substitute for that transport. An absent or blank topic means
that the session is not identified as supervising: the hook MUST allow the turn
to end without discovering or reading repository supervisor markers. A supplied
non-string topic or nonblank topic that is not a single path component other
than `.` or `..` MUST continue the session without probing any marker path.
The hook MUST NOT derive topic ownership from the mere presence of a marker.

For an identified topic, the hook MUST inspect only
`tmp/overseer/<topic>/.supervisor-state` beneath the governed repository's
primary checkout, resolved from the configured `livespec.primaryPath` when
available and otherwise the discovered governed project root. An identified
topic whose governed root cannot be resolved MUST continue without probing
marker paths. Of supervisor markers, the gate MUST read only the owned one.
It MAY independently read the authoritative producer registry and process
identity evidence described below. It MUST refuse path traversal and symlink escapes from that topic's
runtime subtree. It MUST NOT read or change another topic's marker, regardless
of whether that foreign marker is active, malformed or legacy non-JSON state.
A marker MUST be a structured JSON object whose topic matches the identified
topic. Missing, unreadable, malformed, legacy non-JSON or mismatched owned
evidence MUST continue the supervised session; it MUST NOT silently disable the
gate. A valid owned marker with `supervision_active` explicitly false permits
completion regardless of age; freshness applies only while it is true. Missing
or malformed activation state MUST continue the session.

While the owned marker has `supervision_active` true, completion MUST require a
fresh marker (`updated_at`), an empty `open_obligations` array, and a terminal
`completion_disposition` object whose `kind` is either `plan-complete` without a
`question` or `maintainer-blocking` with exactly one nonempty `question` ending
in a single `?`. A valid freshness timestamp MUST include its timezone and MUST be no more than
24 hours old or five minutes in the future. Unknown or malformed completion or
producer evidence MUST continue the session. Local wake producers MUST have a
live PID whose observed command line matches both the expected command and
identity. Forge/CI or ledger producers MUST have their `registered_producer_identity`
independently present in the authoritative producer registry. The registry MAY
be shared at `tmp/overseer/.wake-producers.json` or held in the owned topic
subtree; it MUST NOT be inferred from a foreign topic marker. Every accepted wake producer
MUST name cold-open reentry through the owned marker and a fresh authoritative
ledger, forge or CI query; a promise to check later is insufficient.

The exact real-user command `stop supervising <topic>` for the identified topic
MUST allow completion even when its owned evidence is missing, unreadable,
malformed, legacy non-JSON, stale or mismatched. Assistant
messages, tool results, ordinary user messages, and objective-replacement requests
MUST NOT be treated as that override. On `stop_hook_active` reentry the gate MUST
allow completion without inspecting markers, avoiding recursive Stop blocking.
An unexpected failure while evaluating an identified topic MUST continue that
session rather than grant completion.

## Versioning

`plugin.json.version` is the single source of truth for the shipped
Driver plugin's version and is auto-managed by `release-please` from
per-commit Conventional Commits. `marketplace.json` MUST NOT carry a
`version` field. This mirrors livespec core's `contracts.md`; the Driver follows the same release mechanism for
its own plugin artifact.
