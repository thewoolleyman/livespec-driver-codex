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
# against. The installed supervisor owns observer lifecycle; this provisioner
# only reconciles and reports the newer of its own and the observer's result.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unit="livespec-codex-hook-cache-observer.service"
case "$(uname -s)" in
Darwin)
    label="com.livespec.codex-hook-cache-observer"
    target="gui/$(id -u)/$label"
    if ! launchd_status="$(launchctl print "$target" 2>&1)"; then
        echo "Codex hook-cache observer is not running under the installed LaunchAgent: $label" >&2
        exit 1
    fi
    if [[ "$launchd_status" != *"state = running"* ]]; then
        echo "Codex hook-cache observer is not running under the installed LaunchAgent: $label" >&2
        exit 1
    fi
    launchd_pid="$(printf '%s\n' "$launchd_status" | sed -nE 's/^[[:space:]]*pid = ([0-9]+)$/\1/p' | head -n 1)"
    if [[ -z "$launchd_pid" ]]; then
        echo "Codex hook-cache observer is not running under the installed LaunchAgent: $label" >&2
        exit 1
    fi
    # Keep the status probe as a quiet compatibility check; `provision`
    # below owns the visible per-plugin result after its explicit reconcile.
    python3 "$here/codex_hook_cache_observe.py" status --all --expected-pid "$launchd_pid" >/dev/null 2>&1 || true
    python3 "$here/codex_hook_cache_observe.py" provision --all --expected-pid "$launchd_pid"
    ;;
Linux)
    if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user is-active "$unit" >/dev/null; then
        echo "Codex hook-cache observer is not running under the installed supervisor unit: $unit" >&2
        exit 1
    fi
    python3 "$here/codex_hook_cache_observe.py" status --all >/dev/null 2>&1 || true
    python3 "$here/codex_hook_cache_observe.py" provision --all
    ;;
*)
    echo "Codex hook-cache observer has no supported supervisor on this platform." >&2
    exit 1
    ;;
esac
