#!/usr/bin/env bash
set -uo pipefail

# The gate Job sets LIVESPEC_GATE_CONTEXT after restoring the staged index.
# Its aggregate must run locally there, never submit another Job.
if [[ -z "${LIVESPEC_GATE_CONTEXT:-}" ]]; then
    set +e
    uv run python -m livespec_dev_tooling.pre_commit_delegate run
    delegate_status=$?
    set -e
    case "$delegate_status" in
        0)
            exit 0
            ;;
        75)
            ;;
        *)
            exit "$delegate_status"
            ;;
    esac
fi

exec just check-pre-commit-local
