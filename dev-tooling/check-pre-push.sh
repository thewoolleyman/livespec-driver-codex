#!/usr/bin/env bash
set -uo pipefail

# Ratified shell-quality deviation: this pre-push gate intentionally does not
# use errexit because a green-token miss should fall through to the full check.
if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
    echo ":: pre-push: green token matched; skipping full aggregate"
    exit 0
fi

just check
