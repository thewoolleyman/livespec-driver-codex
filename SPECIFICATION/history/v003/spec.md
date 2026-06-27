# spec.md — livespec-driver-codex

This is the natural-language specification for `livespec-driver-codex`,
the reference **Codex Driver** for the livespec family — the
Codex-runtime analog of `livespec-driver-claude`. The Driver dogfoods
`livespec` — this `SPECIFICATION/` tree evolves through `livespec:seed`
/ `propose-change` / `revise` / `doctor` / `prune-history` / `critique`,
exactly the same lifecycle every consumer project uses.

Throughout this spec, the token "v1" refers to the Driver plugin's first
MAJOR release line (semver `1.x.x`). Pre-1.0 `0.x` releases are bootstrap
territory and do not satisfy any rule scoped to "v1". Rules without a
"v1" qualifier are unconditional and bind every release.

## Purpose

A **Driver** is the thin, agent-runtime-specific wrapper through which a
human drives the livespec spec lifecycle interactively. `livespec-driver-codex`
is the Codex-runtime Driver under livespec's contract-plus-reference-
implementations architecture (per `livespec/SPECIFICATION/spec.md`). It binds livespec
core's harness-neutral material to ONE tool runtime — Codex.

This repo ships exactly three things, all Codex-runtime mechanics:

1. **The eight thin SKILL.md bindings** under `livespec/skills/<name>/`,
   one per spec-side operation (`seed`, `propose-change`, `critique`,
   `revise`, `doctor`, `prune-history`, `next`, `help`). Each binding
   resolves livespec core at runtime, reads core's operation prose, and
   dispatches the config-named spec-side CLI.
2. **A plugin-shipped hook bundle** under `livespec/hooks/` —
   `hooks.json` plus a fail-open `PreToolUse` footgun guard. This is
   Driver-owned runtime surface (unlike the prose and CLIs, which are
   core's).
3. **A structural gate** (`dev-tooling/check_plugin_structure.py`) that
   mechanically enforces the manifest, skill-set, binding-body, and
   invocation invariants this spec codifies.

Everything substantive stays in livespec core: the harness-neutral
operation prose (`prose/<name>.md`), the reference spec-side CLIs
(`scripts/bin/<name>.py`), the JSON schemas, and the built-in templates.
The Driver carries none of those; it resolves them from core at runtime.

## Scope boundary

This spec governs the Driver's own seam — the surface this repo owns and
that nothing upstream governs:

- the plugin and marketplace manifest shape, including the Codex subdir
  layout (`contracts.md` §"Plugin manifest and marketplace");
- the eight-skill binding set and its frontmatter discipline;
- the **core-root resolution algorithm** and its fail-modes;
- the **fenced-invocation discipline** by which a SKILL.md invokes core's
  wrapper CLIs;
- the **hook-bundle wiring** (existence, registration, and the home for
  the guard script and its tests).

Out of scope — these are core-owned and this tree references them, never
restates them: the operation prose contents; the wrapper-CLI surfaces,
exit codes, and wire contracts; the JSON schemas; the built-in templates;
the eight sub-command *names* and any rename (those require a core
propose-change cycle); and the hook *disciplines and postures* (fail-open
contract, deny-vs-warn) — those live in `livespec/SPECIFICATION/contracts.md`. The family-standard primary-checkout commit-refuse
hook is likewise core-owned (`livespec/SPECIFICATION/non-functional-requirements.md`); this repo carries the scaffold but
does not re-specify it.

Upstream-wins: when a rule here conflicts with livespec core's
`SPECIFICATION/`, the upstream rule wins.

## Terminology

The family vocabulary is defined upstream in `livespec/SPECIFICATION/spec.md`
§"Terminology"; this tree uses it without redefinition. The terms that recur here:

- **Driver** — the thin, agent-runtime-specific wrapper (this repo, for
  Codex). Core is agnostic to it.
- **core-root** (`<core-root>`) — the resolved livespec core plugin root
  from which a binding reads prose and dispatches CLIs. Surfaced to the
  bindings as the `$LIVESPEC_CORE_ROOT` shell variable.
- **Binding** — a single `livespec/skills/<name>/SKILL.md` that binds one
  core operation to Codex.
- **Thin-transport binding** — a binding (e.g. `next`) whose whole job is
  to invoke its backing wrapper and present the structured output
  verbatim, with no ranking or judgment in the binding.

## Public surface

The Driver's public, user-facing surface is the eight skills, invoked by
NAME under the Driver plugin name: `livespec:seed`,
`livespec:propose-change`, `livespec:critique`, `livespec:revise`,
`livespec:doctor`, `livespec:prune-history`, `livespec:next`,
`livespec:help`. Codex invocation is name-based — there is no slash-command
form. The sub-command *names* are a core v1 contract; the *runtime
mechanics* that expose them are this repo's.

The human picker surface is distinct from the model/programmatic
colon-qualified name. In the Codex TUI, `/skills` → `List skills` (or the
`@` picker) is searched by the short skill name and renders the owning
plugin as context, e.g. `orchestrate (livespec-orchestrator-beads-fabro)`.
The colon-qualified form (`livespec-orchestrator-beads-fabro:orchestrate`)
remains the name-selection form for prompts, `codex exec`, and model-visible
skill references; it is not the picker row an operator should search for.

The plugin is deliberately NAMED `livespec` (not `livespec-driver-codex`)
so the established `livespec:*` surface is preserved; the marketplace
catalog is named `livespec-driver-codex`. The hook bundle is the second
public surface: a plugin-shipped Codex hook that fires automatically when
the plugin is enabled.

## Lifecycle and evolution

This `SPECIFICATION/` tree is the live spec for the Driver seam and
evolves through the standard livespec loop. The Driver's *behavior* —
what each operation does — is owned by core's operation prose; edits to
behavior happen in livespec core, not here. This repo's spec changes when
the Driver-local seam changes: the manifest shape, the resolution
algorithm, the invocation discipline, the hook bundle's wiring, or the
structural gate. Renaming the plugin or marketplace names, adding or
removing a binding, or changing the hook's posture requires a
propose-change cycle (against this tree for Driver-local mechanics, or
against core for the corresponding upstream contract).
