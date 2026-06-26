# livespec-driver-codex — specification

This tree is the natural-language specification for `livespec-driver-codex`,
the reference **Codex Driver** for the livespec family: the thin,
agent-runtime-specific SKILL.md bindings (plus a small plugin-shipped
footgun-guard hook and a structural gate) through which a human drives
the livespec spec lifecycle interactively. The Driver dogfoods `livespec`
— every change to this `SPECIFICATION/` flows through `livespec:seed` /
`propose-change`, `livespec:critique`, `livespec:revise`,
`livespec:doctor`, and `livespec:prune-history`.

This spec governs ONLY the Driver's own seam. Everything substantive —
the harness-neutral operation prose, the reference spec-side CLIs, the
JSON schemas, and the built-in templates — ships with livespec core and
is governed by `livespec`'s `SPECIFICATION/`. This tree defers to core by
citation and never restates the upstream contract.

## File map

- `spec.md` — purpose, scope boundary, terminology, the public Driver
  surface, and lifecycle. The orienting document; read this first.
- `contracts.md` — the Driver-owned seam contracts: the Codex
  plugin/marketplace manifest shape (subdir layout), the eight-skill
  binding set, the core-root resolution algorithm, the fenced-invocation
  discipline, the hook-bundle surface, and versioning.
- `constraints.md` — architecture-level constraints the bindings honor:
  binding-shape rules, resolution-substrate rules, structural-check
  rules, and forbidden patterns.
- `non-functional-requirements.md` — contributor-facing invariants:
  task-runner discipline, repo layout, the enforcement suite, build and
  release, test discipline, and spec-evolution rules.
- `scenarios.md` — Gherkin scenarios per Driver-owned contract path.

## Read order for a new contributor

1. `spec.md` — what the Driver is and where its boundary sits.
2. `contracts.md` — the seam contracts the bindings and hook bundle hold.
3. `constraints.md` — architectural rules the bindings honor.
4. `non-functional-requirements.md` — how the repo is built, tested, and
   released.
5. `scenarios.md` — the worked examples for each contract path.

## Lifecycle

Every change here lands through livespec's standard loop. Direct edits
outside a `revise` snapshot are out-of-process; doctor's static phase
will flag drift.

## Upstream pointers

When any rule in this tree appears to conflict with `livespec`'s
`SPECIFICATION/`, the upstream rule wins. The Driver's binding contract,
the name-based command surface, the wrapper-CLI shapes, the schemas, and
the hook *disciplines/postures* are all core-owned; this tree governs
only the Driver-local realization of that seam. The `compat.pinned` value
in the repo-root `.livespec.jsonc`'s `livespec-driver-codex` section
records which `livespec` release this spec is currently consistent with.
