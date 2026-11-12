#!/usr/bin/env bash
set -uo pipefail

# Ratified shell-quality deviation: this pre-push gate intentionally does not
# use errexit because a green-token miss should fall through to the full check.
# A matching token memoizes only members whose declarations say the committed
# tree decides their verdict; the world-reading members still run on this host.
targets=()
while read -r target _; do
    if [[ -n "$target" && "$target" != \#* ]]; then
        targets+=("$target")
    fi
done < check-targets.txt

if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
    if ! world_reading="$(
        uv run python -m livespec_dev_tooling.green_token world-reading "${targets[@]}"
    )"; then
        echo ":: pre-push: could not resolve world-reading members" >&2
        exit 1
    fi
    if [[ -z "$world_reading" ]]; then
        echo ":: pre-push: green token matched; no world-reading members"
        exit 0
    fi
    mapfile -t world_reading_targets <<< "$world_reading"
    echo ":: pre-push: green token matched; rerunning world-reading members"
    failed=()
    for target in "${world_reading_targets[@]}"; do
        if ! just "$target"; then
            failed+=("$target")
        fi
    done
    if [ "${#failed[@]}" -gt 0 ]; then
        echo "FAILED targets: ${failed[*]}" >&2
        exit 1
    fi
    exit 0
fi

# A delegating host hands the gate to the remote executor. The exec is
# load-bearing: a delegated run that reaches no verdict must refuse the push and
# never fall through to the local aggregate. A host that cannot read the gates
# kubeconfig (a Fabro sandbox) and the gate pod itself exit `enabled` non-zero
# and run `just check` below.
if uv run python -m livespec_dev_tooling.gate_remote_delegate enabled; then
    echo ":: pre-push: delegating the gate to the remote executor"
    exec uv run python -m livespec_dev_tooling.gate_remote_delegate run
fi

just check
