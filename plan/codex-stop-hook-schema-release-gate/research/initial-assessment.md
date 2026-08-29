# Codex Stop-hook schema release gate

## Incident finding

The supervisor completion gate correctly treated stale YAML `.supervisor-state` markers as malformed and blocked completion. Its block payload, however, reused a PreToolUse-style `hookSpecificOutput` deny object. Codex CLI 0.150.1 accepts Stop output only with the top-level keys `continue`, `decision`, `reason`, `stopReason`, `suppressOutput`, and `systemMessage`; its schema has `additionalProperties: false`. The Stop-hook runtime therefore rejected syntactically valid JSON as invalid output.

## Release gap

Existing tests asserted parseability and `decision == block`, but never validated output against the Stop-event contract. The installed-shape suite proves a hook runs from its packaged root but does not apply Codex Stop schema validation to its stdout. `just check-hooks` and CI ran those incomplete tests, so CI could release the incompatible payload.

## Prevention objective

Make every non-empty stdout payload from every declared Stop hook contract-validated in local hook tests, package/install-shape tests, and the CI hook lane. Keep malformed-marker blocking as a required negative-path case. The checker must reject a deliberately injected `hookSpecificOutput` payload, so the protection is demonstrated rather than merely asserted.

## Candidate implementation slices

1. Introduce one local, versioned Codex Stop output contract helper/schema whose allowlist matches the embedded CLI schema, with unit tests for valid and invalid payloads.
2. Extend each Stop-hook test suite to validate all warning/block stdout against that helper, including supervisor malformed-marker and fail-closed paths plus `systemMessage` warning paths.
3. Extend shipped-hook install-shape coverage to exercise representative non-empty Stop outputs from the copied plugin and validate them through the same contract.
4. Add a dedicated `check-codex-stop-hook-contract` recipe to the aggregate and CI matrix, or make its test an explicit mandatory part of `check-hooks`; decide from existing recipe conventions while avoiding duplicated expensive tests.
5. Add a fixture/contract-drift check tied to the supported Codex CLI version so an upstream Stop schema change fails explicitly and requires a conscious compatibility update.

## Explicit deferrals

- PreToolUse hook contracts are out of scope; their `hookSpecificOutput` use is event-appropriate.
- Changing supervisor-marker semantics is out of scope; malformed YAML must continue to block.
- Automatic runtime downloading or parsing arbitrary Codex installations is deferred unless the compatibility probe can be made hermetic in CI.
