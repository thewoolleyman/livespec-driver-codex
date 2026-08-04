#!/usr/bin/env bash
set -uo pipefail

# Ratified shell-quality deviation: this fixer intentionally does not use
# errexit because unfixable Ruff findings should fall through to later gates.
mapfile -t staged < <(git diff --cached --name-only --diff-filter=AM -- '*.py')
if [ "${#staged[@]}" -eq 0 ]; then
    exit 0
fi

uv run ruff check --fix --exit-zero --force-exclude "${staged[@]}"
uv run ruff format --force-exclude "${staged[@]}"
git add "${staged[@]}"
