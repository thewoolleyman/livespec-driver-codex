# justfile — livespec-driver-codex task runner.
#
# Family conventions, scaled to this repo's content (thin SKILL.md
# bindings + plugin manifests + the plugin-shipped footgun guard + the
# e2e-cli harness consumer):
#
# Authority: livespec/SPECIFICATION/non-functional-requirements.md
#   §"Enforcement-suite invocation" — `just` is the canonical entry
#   point for every dev-tooling invocation. Lefthook and CI MUST
#   delegate to `just <target>`; direct tool invocations in hook/CI
#   configs are banned.
#
# Authority: livespec/SPECIFICATION/contracts.md
#   §"Pre-commit step ordering" — the gates wired here mirror the
#   spec-required ordering: 00-lint-autofix-staged, 01-commit-pairs-
#   source-and-test, 02-check-pre-commit at pre-commit;
#   no-commit-on-master + red-green-replay at commit-msg.
#
# The Red→Green→Replay ritual IS enforced here (epic livespec-gcp2:
# red-green-replay is enforced fleet+adopter-wide, regardless of any
# repo's product-Python footprint). The gate only fires on a
# `feat:`/`fix:` commit that stages a `.py` file; this repo's small
# source surface (the stdlib-only structural check + footgun guard)
# rides the ritual when it changes, exactly as every other family repo
# does. This repo does NOT carry the full canonical check inventory —
# only the layout-relevant subset wired in the `check:` aggregate below.

# Default to listing targets when no recipe is invoked.
default:
    @just --list

# ---------------------------------------------------------------
# First-time setup.
# ---------------------------------------------------------------

# First-touch setup — a THIN delegator to the shipped LOCAL first-touch
# reconcile verb (`livespec_dev_tooling.fleet.local_reconcile`), the
# generalized successor to this recipe's former inline steps (livespec-zs22.8
# M5). Reuse-first: NO copied logic — the verb walks the LOCAL obligation
# partition (`contract.LOCAL_OBLIGATION_ROWS`): mise trust/install, uv sync,
# the structural commit-refuse hooks (subsuming `lefthook install` — the
# canonical hook overwrites the lefthook stubs and delegates to `lefthook
# run`), the advisory `refs/notes/*` refspec, the worktree-root mise-trust
# entry, the beads tenant-dir hardening, the beads-runtime detect-and-guide
# probes, and project-scoped Claude/Codex plugin registration. The plugin rows
# delegate back to THIS repo's own `ensure-plugins` (Claude) and
# `ensure-codex-plugins` (Codex) recipes below; both are now present, so both
# the Claude-plugins and codex-plugins reconcile rows RUN. (Previously this repo
# carried only the Codex provisioner under the `ensure-plugins` name and shipped
# no `ensure-codex-plugins` recipe, so the codex-plugins row SKIPped and the
# Claude-plugins row ran the Codex recipe; the recipe below has been renamed to
# the fleet-standard `ensure-codex-plugins` and a real Claude `ensure-plugins`
# added, so each reconcile row now routes to its own runtime.) The
# verb resolves the target checkout worktree-safely via `git rev-parse
# --git-common-dir`, so invoking from a linked worktree still provisions the
# primary checkout's shared state. Mirrors the `install-commit-refuse-hooks`
# recipe's `uv run python -m ...` from-package invocation.
bootstrap:
    uv run python -m livespec_dev_tooling.fleet.local_reconcile

# Install the canonical livespec commit-refuse hook by REUSING the shared
# livespec-dev-tooling installer module (the SINGLE source of the structural
# hook body; pinned in pyproject.toml). NOT re-implemented in this Driver repo.
# Idempotent; worktree-safe (resolves the primary's shared .git/hooks).
install-commit-refuse-hooks:
    uv run python -m livespec_dev_tooling.install_commit_refuse_hooks

# The standard shared derive-from-settings wrapper: reads the committed
# `.claude/settings.json` (`extraKnownMarketplaces` incl. ref, `enabledPlugins`)
# at runtime and issues the marketplace add / install / update commands for
# exactly what it finds — one source of truth, recipe-content drift structurally
# impossible. Registers this repo's full project-scope Claude plugin set; the
# SessionStart hook in `.claude/settings.json` runs this recipe so each new
# session's project-scope plugins are current. Core + the Claude Driver MUST be
# present for agents doing Claude-side work in this repo, even though this repo's
# own published surface is the Codex Driver (the Codex plugins are registered
# host-wide by `ensure-codex-plugins` below).
ensure-plugins:
    mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins

# Idempotent host-wide Codex plugin provisioning. Codex does not support
# project-scoped plugin enablement, so these registrations intentionally land in
# the user's default CODEX_HOME and are visible to every repo on the host. Codex
# is an optional dogfooding runtime; bootstrap skips this target when the CLI is
# absent but fails on real install errors when Codex is present. Named
# `ensure-codex-plugins` (the fleet-standard name) so local_reconcile's
# codex-plugins row routes to it by name; it was formerly the `ensure-plugins`
# recipe, which mislabeled Codex provisioning as the Claude-plugins row.
ensure-codex-plugins:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v codex >/dev/null 2>&1; then
        echo "codex CLI not found; skipping host-wide Codex plugin install." >&2
        exit 0
    fi
    codex plugin marketplace add thewoolleyman/livespec --ref release
    codex plugin marketplace add thewoolleyman/livespec-driver-codex --ref release
    codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro --ref release
    codex plugin marketplace upgrade livespec
    codex plugin marketplace upgrade livespec-driver-codex
    codex plugin marketplace upgrade livespec-orchestrator-beads-fabro
    codex plugin add livespec@livespec
    codex plugin add livespec@livespec-driver-codex
    codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro

# ---------------------------------------------------------------
# Enforcement aggregate.
# ---------------------------------------------------------------

check:
    #!/usr/bin/env bash
    set -uo pipefail
    targets=(
        check-plugin-structure
        check-plugin-resolution
        check-lint
        check-format
        check-hooks
        check-e2e-cli
        check-codex-skill-picker
        check-heading-coverage
        check-doctor-static
        check-all-declared
        check-assert-never-exhaustiveness
        check-comment-line-anchors
        check-file-lloc
        check-global-writes
        check-keyword-only-args
        check-main-guard
        check-match-keyword-only
        check-no-inheritance
        check-no-lloc-soft-warnings
        check-no-write-direct
        check-partition-completeness
        check-private-calls
        check-rop-pipeline-shape
    )
    failed=()
    for target in "${targets[@]}"; do
        echo "=== just ${target} ==="
        if ! just "${target}"; then
            failed+=("${target}")
        fi
    done
    if [ "${#failed[@]}" -gt 0 ]; then
        echo "FAILED targets: ${failed[*]}" >&2
        exit 1
    fi
    # Advisory-local green token — keyed on the current HEAD tree-hash so
    # check-pre-push can skip the full aggregate on a clean, unchanged tree.
    # || true: a write failure must never abort a successful check aggregate.
    # STRICTLY advisory-local; CI remains authoritative.
    uv run python -m livespec_dev_tooling.green_token write || true

# Structural gate for the Codex plugin bundle: marketplace + manifest
# validity (subdir layout), the 8-skill set, frontmatter names +
# descriptions, the Codex core-resolution invocation + Claude-marker
# bans in each body, the fenced-invocation rules (must use
# $LIVESPEC_CORE_ROOT; never `uv run`, never a literal .claude-plugin
# path, never the Driver's own plugin-root placeholder), and the hook
# bundle (hooks.json without a top-level description, PreToolUse/Bash
# wired to the guard). Consumed from the livespec-dev-tooling package
# (`livespec_dev_tooling.driver_checks.plugin_structure`, profile-auto-detecting).
check-plugin-structure:
    uv run python -m livespec_dev_tooling.driver_checks.plugin_structure

# Conformance-Pattern baseline Verifier (shipped by livespec-dev-tooling):
# the cross-harness plugin-resolution concern (concern #2). It reads the
# `harnesses` declaration in `.livespec.jsonc` and, in mock mode, asserts
# declaration integrity (every declared harness has a valid status; an
# exempt harness carries a reason). This repo declares codex SUPPORTED and
# claude EXEMPT, so the mock-mode declaration-integrity pass is the gate
# wired here; codex's genuine live resolution smoke is delegated to the
# repo-local check-codex-skill-picker. Authority: livespec/SPECIFICATION/
# non-functional-requirements.md §"Conformance Pattern".
check-plugin-resolution:
    uv run python -m livespec_dev_tooling.checks.plugin_resolution

check-lint:
    uv run ruff check .

check-format:
    uv run ruff format --check .

# Plugin-shipped Codex hook script (livespec/hooks/) — the footgun
# guard, unit-tested as a subprocess with a JSON stdin payload, asserting
# on the emitted hookSpecificOutput.permissionDecision.
check-hooks:
    uv run pytest tests/hooks/

# CLI end-to-end harness consumer (mock tier) — adapted from the Claude
# Driver. Real structural skill discovery against the in-repo Codex
# plugin source, real fixture loading, the real fail-closed coverage
# gate; only the live `codex` subprocess is gated behind
# LIVESPEC_E2E_HARNESS=real (the `codex` CLI is not guaranteed in CI).
# Harness ships from livespec-dev-tooling per livespec/
# SPECIFICATION/contracts.md §"CLI end-to-end harness contract".
check-e2e-cli:
    LIVESPEC_E2E_HARNESS=mock uv run pytest tests/e2e-cli/

# Live Codex TUI `/skills` picker acceptance. This is the only gate that
# exercises the human picker path: `/skills` -> "List skills" -> search for the
# short skill name `drive` and require the picker to render the
# `drive (livespec-orchestrator-beads-fabro)` Skill row. CI skips unless
# a runner explicitly opts in because GitHub-hosted CI does not provide an
# authenticated interactive Codex TUI.
check-codex-skill-picker:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "${CI:-}" == "true" && "${LIVESPEC_REQUIRE_CODEX_TUI_PICKER:-}" != "1" ]]; then
        echo ":: check-codex-skill-picker: skipped in CI; set LIVESPEC_REQUIRE_CODEX_TUI_PICKER=1 on an authenticated Codex runner to enforce it"
        exit 0
    fi
    if ! command -v codex >/dev/null 2>&1; then
        echo ":: check-codex-skill-picker: codex CLI not found; skipping live TUI picker acceptance"
        exit 0
    fi
    LIVESPEC_E2E_HARNESS=real LIVESPEC_CODEX_SKILL_PICKER=1 uv run pytest tests/e2e-cli/test_codex_skill_picker.py -v

# Spec heading-coverage gate (shipped by livespec-dev-tooling): every
# `## ` H2 in each SPECIFICATION/ NLSpec file MUST have an entry in
# tests/heading-coverage.json. This keeps the coverage map in lockstep
# with the spec — adding or renaming a spec H2 without updating the
# registry fails the check. TODO entries (no per-heading test yet) warn
# locally and fail only when LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST
# is set; this binding repo leaves it UNSET (its H2s are guarded by
# check-plugin-structure / the hook tests / the e2e-cli harness rather
# than per-heading unit tests), so the gate enforces registration drift,
# not test-mapping completeness. The livespec doctor static phase stays
# on-demand via livespec:doctor (no family repo wires it into CI).
check-heading-coverage:
    uv run python -m livespec_dev_tooling.checks.heading_coverage

# livespec core's doctor STATIC phase (reference-discipline + out-of-band
# invariants) against THIS repo's SPECIFICATION/ tree, wired fleet-wide per
# livespec epic livespec-6jfq. core ships the checker: doctor_static.py is
# self-contained (vendored deps + bare python3), so it runs under plain
# python3 and NEVER `uv run`. Resolve core's plugin root via
# LIVESPEC_CORE_PLUGIN_ROOT (CI sets it to a livespec checkout at this repo's
# .livespec.jsonc compat.pinned tag) → else the installed livespec@livespec
# plugin cache (local dev). The two reference-discipline checks
# (no-cross-spec-reference, no-spec-section-citation-in-code) are pure reads;
# doctor-out-of-band-edits is self-healing — on a drifted tree it writes a
# history backfill into the worktree and fails, and committing that backfill
# heals the track; on a clean tree it never fires.
check-doctor-static:
    #!/usr/bin/env bash
    set -euo pipefail
    core_root="${LIVESPEC_CORE_PLUGIN_ROOT:-}"
    if [ -z "$core_root" ]; then
      # Resolve the CURRENT released core build (== marketplace clone HEAD), NOT
      # installed_plugins.json[...]["livespec@livespec"][0] — that per-project list is
      # unordered and its first row can be a different, stale project on a mixed-build
      # host, which the c1k9 currency gate then correctly blocks (livespec-q2me).
      core_root="$(python3 -c 'import subprocess, pathlib; mk = pathlib.Path.home() / ".claude" / "plugins" / "marketplaces" / "livespec"; head = subprocess.run(["git", "-C", str(mk), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True).stdout.strip().lower(); cache = pathlib.Path.home() / ".claude" / "plugins" / "cache" / "livespec" / "livespec" / head; print(cache if head and (cache / "scripts" / "bin" / "doctor_static.py").is_file() else "")' 2>/dev/null || true)"
    fi
    if [ -z "$core_root" ] || [ ! -f "$core_root/scripts/bin/doctor_static.py" ]; then
      echo "livespec core not found. Set LIVESPEC_CORE_PLUGIN_ROOT to a livespec checkout's .claude-plugin, or install the livespec@livespec plugin (claude plugin install livespec@livespec)." >&2
      exit 1
    fi
    python3 "$core_root/scripts/bin/doctor_static.py" --project-root .

# ---------------------------------------------------------------
# Applies-to-all structural coverage checks (fleet-check-coverage,
# livespec epic livespec-i5ebqd). Each derives its file universe from
# the SAME root-anchored git index (`resolve_check_universe`), so this
# thin Driver's three first-party hook `.py` (livespec/hooks/
# block_auto_memory.py + livespec_footgun_guard.py + no_shadow_ledger.py)
# are now structurally covered. These stay Phase-0 WARN-only (exit 0) for
# THIS repo: `file_lloc_hard_gate` is DELIBERATELY NOT set in pyproject's
# [tool.livespec_dev_tooling] yet, because livespec_footgun_guard.py is
# 263 LLOC (over the 250 hard ceiling). Arming the gate is DEFERRED to the
# footgun-guard decomposition follow-up, which genuinely reduces it ≤250
# (never shaved) and only THEN flips file_lloc for this repo — see the
# pyproject block's deferred-flip note. `check-aggregate-completeness` is
# DELIBERATELY NOT wired: it is the universal-propagation gate that
# requires the full canonical spec/orchestrator/copier check set, which a
# thin per-runtime binding does not carry — Drivers stay OUTSIDE
# universal-propagation (maintainer decision 2026-07-12).
# ---------------------------------------------------------------

check-all-declared:
    uv run python -m livespec_dev_tooling.checks.all_declared

check-assert-never-exhaustiveness:
    uv run python -m livespec_dev_tooling.checks.assert_never_exhaustiveness

check-comment-line-anchors:
    uv run python -m livespec_dev_tooling.checks.comment_line_anchors

check-file-lloc:
    uv run python -m livespec_dev_tooling.checks.file_lloc

check-global-writes:
    uv run python -m livespec_dev_tooling.checks.global_writes

check-keyword-only-args:
    uv run python -m livespec_dev_tooling.checks.keyword_only_args

check-main-guard:
    uv run python -m livespec_dev_tooling.checks.main_guard

check-match-keyword-only:
    uv run python -m livespec_dev_tooling.checks.match_keyword_only

check-no-inheritance:
    uv run python -m livespec_dev_tooling.checks.no_inheritance

check-no-lloc-soft-warnings:
    uv run python -m livespec_dev_tooling.checks.no_lloc_soft_warnings

check-no-write-direct:
    uv run python -m livespec_dev_tooling.checks.no_write_direct

check-partition-completeness:
    uv run python -m livespec_dev_tooling.checks.partition_completeness

check-private-calls:
    uv run python -m livespec_dev_tooling.checks.private_calls

check-rop-pipeline-shape:
    uv run python -m livespec_dev_tooling.checks.rop_pipeline_shape

# ---------------------------------------------------------------
# Red→Green→Replay ritual gates (epic livespec-gcp2). Shared from
# livespec-dev-tooling; the recipe bodies are copied verbatim from the
# compliant consumer (livespec-orchestrator-beads-fabro). The gate only
# fires on a `feat:`/`fix:` commit that stages a `.py` file — a `ci:` /
# `docs:` / `chore:` changeset rides through untouched.
# ---------------------------------------------------------------

# Trailer-based Red→Green replay verification (hard gate). Invoked by
# the lefthook commit-msg stage with the commit-message file path as
# argv[1] (the load-bearing per-commit verifier). The no-arg variant
# (e.g. from `just check`) DERIVES the message from `git log -1
# --format=%B` (HEAD) and validates it.
check-red-green-replay *args:
    uv run python -m livespec_dev_tooling.checks.red_green_replay {{args}}

# Commit-pair gate: every commit touching source files also touches
# tests. Lefthook pre-commit is the load-bearing per-commit invocation.
# The source-tree role keys come from this repo's `[tool.livespec_dev_
# tooling]` block in pyproject.toml.
check-commit-pairs-source-and-test:
    uv run python -m livespec_dev_tooling.checks.commit_pairs_source_and_test

# ---------------------------------------------------------------
# Pre-commit auxiliary gates.
# ---------------------------------------------------------------

# Ruff fix + format on staged .py files BEFORE the rest of the
# pre-commit gate runs. Non-blocking — unfixable issues fall through
# to check-lint / check-format inside `just check` later. Re-stages
# post-autofix bytes.
#
# `--force-exclude` on BOTH ruff invocations: ruff normally honors
# `extend-exclude` only for directory-walked paths, NOT for files passed
# explicitly on argv. This recipe passes the staged set explicitly, so
# without `--force-exclude` ruff would lint/format `livespec/hooks/**`
# (which pyproject.toml's `[tool.ruff].extend-exclude` deliberately
# excludes) — silently rewriting the plugin-shipped hook bodies. That
# bug stripped `# noqa: BLE001` from the single-sourced no_shadow_ledger
# body, breaking its byte-identity with the claude Driver's copy.
# `--force-exclude` makes the explicit-path runs honor the exclude.
lint-autofix-staged:
    #!/usr/bin/env bash
    set -uo pipefail
    staged=$(git diff --cached --name-only --diff-filter=AM | grep -E '\.py$' || true)
    if [[ -z "$staged" ]]; then
        exit 0
    fi
    echo "$staged" | xargs uv run ruff check --fix --exit-zero --force-exclude
    echo "$staged" | xargs uv run ruff format --force-exclude
    echo "$staged" | xargs git add

# Fast pre-commit subset (no test run; pre-push runs the full
# aggregate).
check-pre-commit:
    just check-plugin-structure
    just check-lint
    just check-format

check-pre-push:
    #!/usr/bin/env bash
    set -uo pipefail
    # Advisory-local green-token short-circuit: if the current HEAD tree was
    # already verified clean by a successful full `just check` run, skip the
    # full aggregate. The token is invalidated by any new commit (tree-hash
    # change) or an uncommitted worktree modification. STRICTLY advisory-local;
    # CI is authoritative — a token match never bypasses the remote gate.
    if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
        echo ":: pre-push: green token matched — tree byte-identical to last green check; skipping full aggregate (CI is authoritative)"
        exit 0
    fi
    just check
