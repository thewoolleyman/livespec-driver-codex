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
# This repo carries NO product Python beyond the stdlib-only structural
# check and the stdlib-only footgun guard (the only other .py is the
# test suite), so the red-green-replay ritual and the full canonical
# check inventory do not apply here.

# Default to listing targets when no recipe is invoked.
default:
    @just --list

# ---------------------------------------------------------------
# First-time setup.
# ---------------------------------------------------------------

bootstrap:
    # Idempotent `livespec.primaryPath` on the primary checkout's
    # git-common-dir config (family-wide invariant per livespec/
    # SPECIFICATION/non-functional-requirements.md §"Primary-checkout
    # commit-refuse hook" / §"Commit-refuse hook bootstrap procedure").
    # The commit-refuse hook reads this config value to recognize the
    # primary checkout and refuse commits/pushes there, forcing every
    # edit through `git worktree add`.
    git config --file "$(git rev-parse --git-common-dir)/config" livespec.primaryPath "$(realpath "$(dirname "$(git rev-parse --git-common-dir)")")"
    # Install the consolidated git-hook-wrapper.sh as the pre-commit,
    # pre-push, AND commit-msg hooks. The single file carries BOTH the
    # canonical commit-refuse fingerprint (refuses at the primary
    # checkout) and the mise-managed lefthook delegation (fires the
    # per-hook gates at secondary worktrees), so one script satisfies the
    # refuse-at-primary contract and the gate-delegation everywhere. Uses
    # the git-common-dir hooks dir so the install is worktree-safe: from a
    # secondary worktree `.git` is a file and `mkdir -p .git/hooks` would
    # fail, whereas git-common-dir resolves to the shared hooks dir from
    # both the primary checkout and any worktree.
    mkdir -p "$(git rev-parse --git-common-dir)/hooks"
    cp dev-tooling/git-hook-wrapper.sh "$(git rev-parse --git-common-dir)/hooks/pre-commit"
    cp dev-tooling/git-hook-wrapper.sh "$(git rev-parse --git-common-dir)/hooks/pre-push"
    cp dev-tooling/git-hook-wrapper.sh "$(git rev-parse --git-common-dir)/hooks/commit-msg"
    chmod +x "$(git rev-parse --git-common-dir)/hooks/pre-commit" "$(git rev-parse --git-common-dir)/hooks/pre-push" "$(git rev-parse --git-common-dir)/hooks/commit-msg"
    just ensure-plugins

# Idempotent: `codex plugin marketplace add` / `codex plugin add`
# exit 0 (or no-op) when the target is already present. Core MUST be
# installed alongside this Driver — the bindings resolve core's
# prose/ and scripts/ from the installed livespec@livespec cache.
ensure-plugins:
    codex plugin marketplace add thewoolleyman/livespec
    codex plugin marketplace add thewoolleyman/livespec-driver-codex
    codex plugin add livespec@livespec
    codex plugin add livespec@livespec-driver-codex

# ---------------------------------------------------------------
# Enforcement aggregate.
# ---------------------------------------------------------------

check:
    #!/usr/bin/env bash
    set -uo pipefail
    targets=(
        check-plugin-structure
        check-lint
        check-format
        check-hooks
        check-e2e-cli
        check-heading-coverage
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
# wired to the guard). Stdlib-only — runs under bare python3.
check-plugin-structure:
    python3 dev-tooling/check_plugin_structure.py

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
