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

# The install sequence above may have replaced the versioned hook-cache
# directory that already-running sessions captured their hook commands
# against. Reconcile the alias topology, then make sure the observer that
# catches Codex's own startup auto-upgrades is running — both are hard
# failures, because a silently-unrepaired cache means hooks that no longer
# fire while everything still reports installed.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$here/codex_hook_cache_reconcile.py"
python3 "$here/codex_hook_cache_observe.py" ensure
