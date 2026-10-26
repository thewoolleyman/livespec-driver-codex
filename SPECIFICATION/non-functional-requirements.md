# non-functional-requirements.md — livespec-driver-codex

Contributor-facing invariants: how this repo is structured, guarded,
built, tested, and evolved. Where `contracts.md` says *what must be true*
of the Driver seam, this file says *how it is guarded* and how the repo
is operated.

## Boundary

This file covers the operational disciplines of developing the Driver
plugin: the task runner, the repo layout, the enforcement suite that
guards the contracts, the build/release flow, test discipline, and
spec-evolution rules. It does not restate the seam contracts themselves
(`contracts.md`) or the architectural constraints (`constraints.md`).

## Inherited from livespec

The family-standard operational disciplines apply here unmodified and are
owned upstream:

- **Primary-checkout commit-refuse hook** — every change uses a worktree
  → PR → merge → cleanup path; the primary checkout refuses direct
  commits/pushes. The hook body and its doctor fingerprint invariant are
  owned by `livespec/SPECIFICATION/non-functional-requirements.md`
  and `livespec/SPECIFICATION/contracts.md`. This repo carries a
  copy of the canonical scaffold under `dev-tooling/`; it does not
  re-specify it.
- **Toolchain pinning** via `mise`; **`uv`** as the Python toolchain
  manager. Git operations that must fire lefthook are run through
  `mise exec -- git …`; `--no-verify` is never used.

## Task-runner discipline

`just` is the single source of truth for every dev-tooling invocation.
`lefthook` (pre-commit / pre-push) and CI delegate to `just <target>`;
neither invokes a tool binary directly. `just check` is the full
enforcement aggregate and is the load-bearing safety net — it runs
locally, in pre-push, and in CI.

## Repo layout

| Path | Purpose |
|---|---|
| `.agents/plugins/marketplace.json` | The marketplace catalog (`livespec-driver-codex`), listing the single `livespec` plugin sourced from `./livespec` |
| `livespec/` | The Driver plugin: `.codex-plugin/plugin.json`, the eight `skills/<name>/SKILL.md` bindings, and the `hooks/` bundle (`hooks.json` + `livespec_footgun_guard.py`) |
| `dev-tooling/` | `check_plugin_structure.py` (the structural gate), the family-standard git-hook scaffold, and the Codex hook-cache compatibility reconciler + observer executables |
| `tests/dev-tooling/` | Tests for the hook-cache compatibility reconciler and observer: a deterministic mock-cache integration test plus a host-aware real release-tracking transition test |
| `tests/e2e-cli/` | The CLI end-to-end harness consumer (mock-tier skill discovery + fail-closed fixture coverage gate + static binding assertions) |
| `tests/hooks/` | Unit tests for the plugin-shipped footgun guard |
| `SPECIFICATION/` | This spec tree (dogfooded) |
| `justfile`, `lefthook.yml`, `.mise.toml`, `.python-version`, `pyproject.toml` | Family-standard toolchain configuration |

## Enforcement suite

`just check` aggregates the gates that guard the `contracts.md` seam:

- **`check-plugin-structure`** — runs `dev-tooling/check_plugin_structure.py`
  (stdlib-only, fail-closed) to enforce the manifest, skill-set,
  binding-body, fenced-invocation, and hook-bundle contracts in
  `contracts.md`. This is the mechanical teeth behind §"Plugin manifest
  and marketplace", §"Skill-binding set", §"Core-root resolution",
  §"Fenced-invocation discipline", and §"Hook bundle".
- **`check-hooks`** — unit-tests the plugin-shipped footgun guard.
- **`check-e2e-cli`** — drives the CLI end-to-end harness (mock tier).
- **`check-codex-skill-picker`** — drives the live Codex TUI `/skills`
  picker on authenticated local Codex hosts. It opens `/skills`, chooses
  `List skills`, searches `drive`, and fails unless the picker
  renders the `drive (livespec-orchestrator-beads-fabro)` Skill row.
  GitHub-hosted CI skips this gate unless an authenticated runner opts in
  with `LIVESPEC_REQUIRE_CODEX_TUI_PICKER=1`.
- **`check-dev-tooling`** — runs the `tests/dev-tooling/` suite: a
  deterministic mock-cache integration test for the hook-cache
  reconciler/observer (discovery, validation, one-hop retargeting,
  idempotent rerun), plus a host-aware real release-tracking
  transition test that starts a session against an old Driver hook
  path, advances the marketplace/plugin cache, and verifies each
  retained hook path resolves to the validated current payload.
  GitHub-hosted CI skips the real-transition leg unless an
  authenticated runner opts in with
  `LIVESPEC_REQUIRE_CODEX_CACHE_TRANSITION=1`, mirroring
  `check-codex-skill-picker`'s lever.
- **`check-heading-coverage`** — enforces that every `## ` H2 in this
  spec tree maps to an entry in `tests/heading-coverage.json`.
- **`check-lint`** / **`check-format`** — `ruff` lint and format gates.

Every gate is wired into both pre-commit/pre-push (via lefthook) and CI
(via the per-target matrix in `.github/workflows/ci.yml`), so the same
suite runs in every context.

Where the repository has delegated its pre-push gate per the next
paragraph, a pre-push from a delegating host obtains the same `just
check` aggregate's verdict from the remote executor against the pushed
tree instead of running it on the pushing host, save the checks the
delegation contract places on the pushing host, and except where an
explicit local run has already authorized the tree. This changes WHERE
the aggregate runs and MUST NOT change WHAT it verifies.

The repository MAY delegate its pre-push gate to the remote executor of
the fleet enforcement suite's delegation client (livespec-dev-tooling
§"Delegated pre-push gate"). When it does, it MUST conform to the
delegation contract livespec ratifies in
§"Enforcement-suite invocation", clause **Delegated gate execution**.
For this repository that means:

- Delegation MUST be opted in by the repository's version-controlled
  configuration. It MUST be withdrawn only by a change to that
  configuration, never per push or per host. The gate MUST remain
  runnable on the pushing host by an explicit act whether or not
  delegation is opted in.
- A push MUST delegate only from a host that holds the credential
  authorizing it to submit to the executor. A host that holds none, such
  as a factory sandbox, MUST run the repository's gate recipe on that
  host without delegation, and MUST report that it gated locally.
- The pre-push path for a delegating host MUST run the delegation client
  in place of the aggregate, and MUST have no branch from the client's
  result to a local run of the gate. An absent verdict MUST refuse the
  push.
- A check that reads an authorization held outside the tree MUST run on
  the pushing host with that host's own credentials, not in the
  executor, and its result MUST join the delegated verdict, so an
  authorization the executor cannot read is never treated as granted.
- The check recipe MUST read the fleet's recognised skip variable,
  `SKIP_TARGETS`, so the members the delegation contract places on the
  pushing host are left out of the executor's run. A run that skipped
  any member MUST NOT write the green token.

## Build and release

The Driver ships as a Codex plugin. `plugin.json.version` is the single
source of truth for the shipped version and is auto-managed by
`release-please` from Conventional Commits (`contracts.md` §"Versioning").

## Test discipline

Three test surfaces back the enforcement suite: `tests/e2e-cli/` proves the
Driver bindings drive core's wrappers — the CI-safe mock tier runs real
structural skill discovery against the in-repo Codex plugin, real fixture
loading, the real fail-closed coverage gate, and static binding
assertions, with NO live `codex` subprocess (a live round-trip is gated
behind `LIVESPEC_E2E_HARNESS=real` since the `codex` CLI is not
guaranteed in CI). A separate live TUI picker acceptance in the same
directory covers the human `/skills` discovery path and is intentionally
host-aware: it runs where Codex is present and authenticated, but skips on
GitHub-hosted CI unless the runner explicitly opts in. `tests/hooks/`
unit-tests the footgun guard via subprocess invocation with a JSON stdin
payload, asserting on the emitted `hookSpecificOutput.permissionDecision`.
`tests/dev-tooling/` proves the Codex hook-cache compatibility reconciler
and observer: a deterministic mock-cache integration test covers
discovery, validation, one-hop retargeting, and idempotent rerun; a
host-aware real release-tracking transition test — gated the same way as
the live TUI picker acceptance above — starts a session against an old
Driver hook path, advances the marketplace/plugin cache, and verifies
each retained hook path resolves to the validated current payload.

## Spec evolution

This `SPECIFICATION/` tree dogfoods livespec. Every change lands through
`livespec:propose-change` → `livespec:revise`, which snapshots the result
under `history/vNNN/`. `livespec:doctor`'s static phase flags
out-of-process drift, and `check-heading-coverage` mechanically enforces
that the spec's H2 set stays in lockstep with `tests/heading-coverage.json`.
