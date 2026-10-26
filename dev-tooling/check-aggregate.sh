#!/usr/bin/env bash
set -uo pipefail

# Ratified shell-quality deviation: this aggregate intentionally does not use
# errexit because it must run every target and report the complete failure set.
# check-targets.txt keeps the canonical block visible to the shared aggregate
# verifier while this runner stays ShellCheck-governed.
# Arguments name targets to skip. The `check` recipe passes the fleet's
# SKIP_TARGETS list here; a run that skipped anything writes no green token.
skip_targets=("$@")

targets=()
while IFS= read -r target; do
    if [[ -n "$target" && "$target" != \#* ]]; then
        targets+=("$target")
    fi
done < check-targets.txt

failed=()
coverage_ran=0
for target in "${targets[@]}"; do
    skip_this=0
    for skipped in "${skip_targets[@]}"; do
        if [[ "$target" = "$skipped" ]]; then
            skip_this=1
        fi
    done
    if [[ "$skip_this" -eq 1 ]]; then
        echo "::: just ${target} (skipped)"
        continue
    fi
    if [[ "$target" = "check-coverage" && "$coverage_ran" -eq 1 ]]; then
        continue
    fi
    echo "=== just ${target} ==="
    if ! just "${target}"; then
        failed+=("${target}")
    fi
    if [ "$target" = "check-per-file-coverage" ]; then
        coverage_ran=1
    fi
done

if [ "${#failed[@]}" -gt 0 ]; then
    echo "FAILED targets: ${failed[*]}" >&2
    exit 1
fi

if [ "${#skip_targets[@]}" -gt 0 ]; then
    echo ":: skipped ${skip_targets[*]}: no green token written"
    exit 0
fi

if ! uv run python -m livespec_dev_tooling.green_token write; then
    :
fi
