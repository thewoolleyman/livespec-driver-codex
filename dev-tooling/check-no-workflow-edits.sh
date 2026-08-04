#!/usr/bin/env bash
set -euo pipefail

base_ref="${LIVESPEC_FACTORY_BASE_REF:-master}"
if ! git diff --quiet "${base_ref}...HEAD" -- .github/workflows; then
    echo "Factory branch boundary violation: .github/workflows differs from ${base_ref}." >&2
    git diff "${base_ref}...HEAD" -- .github/workflows >&2
    exit 1
fi
