#!/usr/bin/env bash
set -uo pipefail

# Ratified shell-quality deviation: this pre-push gate intentionally does not
# use errexit because a green-token miss should fall through to the full check.
if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
    echo ":: pre-push: green token matched; skipping full aggregate"
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
