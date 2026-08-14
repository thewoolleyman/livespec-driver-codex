#!/usr/bin/env bash
set -euo pipefail

# The deterministic mock-cache leg always runs: it needs no Codex install and
# no host cache, so there is nothing for CI to opt into.
uv run pytest tests/dev-tooling/ \
    --ignore=tests/dev-tooling/test_codex_hook_cache_transition_real.py

if [[ "${CI:-}" == "true" && "${LIVESPEC_REQUIRE_CODEX_CACHE_TRANSITION:-}" != "1" ]]; then
    echo ":: check-dev-tooling: real release-tracking transition leg skipped in CI; set LIVESPEC_REQUIRE_CODEX_CACHE_TRANSITION=1 on an authenticated Codex runner to enforce it"
    exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
    echo ":: check-dev-tooling: codex CLI not found; skipping the real release-tracking transition leg"
    exit 0
fi

LIVESPEC_REQUIRE_CODEX_CACHE_TRANSITION=1 \
    uv run pytest tests/dev-tooling/test_codex_hook_cache_transition_real.py -v
