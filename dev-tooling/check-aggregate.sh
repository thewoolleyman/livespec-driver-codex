#!/usr/bin/env bash
set -uo pipefail

# Ratified shell-quality deviation: this aggregate intentionally does not use
# errexit because it must run every target and report the complete failure set.
# check-targets.txt keeps the canonical block visible to the shared aggregate
# verifier while this runner stays ShellCheck-governed.
targets=()
while IFS= read -r target; do
    if [[ -n "$target" && "$target" != \#* ]]; then
        targets+=("$target")
    fi
done < check-targets.txt

failed=()
coverage_ran=0
for target in "${targets[@]}"; do
    if [ "$target" = "check-per-file-coverage" ]; then
        echo "=== just check-coverage (prerequisite for check-per-file-coverage) ==="
        if ! just check-coverage; then
            failed+=("check-coverage")
            coverage_ran=1
            continue
        fi
        coverage_ran=1
    fi
    if [[ "$target" = "check-coverage" && "$coverage_ran" -eq 1 ]]; then
        continue
    fi
    echo "=== just ${target} ==="
    if ! just "${target}"; then
        failed+=("${target}")
    fi
done

if [ "${#failed[@]}" -gt 0 ]; then
    echo "FAILED targets: ${failed[*]}" >&2
    exit 1
fi

if ! uv run python -m livespec_dev_tooling.green_token write; then
    :
fi
