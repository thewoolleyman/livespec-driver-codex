"""Versioned contract helper for Codex Stop-hook stdout.

Provenance
----------
Supported runtime: **Codex CLI 0.150.1** (`SUPPORTED_CODEX_CLI_VERSION`). That
release's hook-output schema declares the Stop event's top-level object CLOSED —
`additionalProperties: false` over exactly six optional keys: `continue`,
`decision`, `reason`, `stopReason`, `suppressOutput`, `systemMessage`. Value
types mirror the shared hook-output schema those keys come from: the two
`continue`/`suppressOutput` flags are booleans and the remaining four are
strings.

The key set is transcribed here rather than fetched, because the Codex install
is not available to CI and downloading one at test time was explicitly deferred
(`plan/codex-stop-hook-schema-release-gate/research/initial-assessment.md`).
That same note records why the contract exists: a Stop hook shipped a
PreToolUse-style `hookSpecificOutput` deny object, and the Stop runtime rejected
the syntactically valid JSON. Tests asserted parseability and `decision ==
block`, so nothing caught it before release.

Scope
-----
This helper validates the TOP-LEVEL Stop-output object only — its closed key set
and each present key's value type. PreToolUse output is deliberately NOT
validated here: `hookSpecificOutput` is event-appropriate there, and this helper
exists precisely to reject it on the Stop seam.

When the supported Codex CLI moves, bump `SUPPORTED_CODEX_CLI_VERSION` and the
key/type table together, so a runtime schema change is a conscious compatibility
update rather than a silent drift.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final, cast

from returns.result import Failure, Result, Success

__all__: list[str] = [
    "PRE_TOOL_USE_ONLY_KEY",
    "STOP_OUTPUT_ALLOWED_KEYS",
    "SUPPORTED_CODEX_CLI_VERSION",
    "SUPPORTED_SCHEMA_PROVENANCE",
    "validate_stop_output",
]

SUPPORTED_CODEX_CLI_VERSION: Final = "0.150.1"

SUPPORTED_SCHEMA_PROVENANCE: Final = (
    "Codex CLI 0.150.1 hook-output schema: the Stop event's top-level object is closed "
    "(additionalProperties: false) over exactly continue, decision, reason, stopReason, "
    "suppressOutput, systemMessage. Transcribed into this repo because CI has no Codex "
    "install to read the schema from; see "
    "plan/codex-stop-hook-schema-release-gate/research/initial-assessment.md for the "
    "incident that made the contract load-bearing."
)

# The PreToolUse-only field whose appearance in Stop output caused the incident.
# Named as a constant so the negative-path assertion reads as the contract it is.
PRE_TOOL_USE_ONLY_KEY: Final = "hookSpecificOutput"

_STOP_OUTPUT_VALUE_TYPES: Final[Mapping[str, type]] = {
    "continue": bool,
    "decision": str,
    "reason": str,
    "stopReason": str,
    "suppressOutput": bool,
    "systemMessage": str,
}

STOP_OUTPUT_ALLOWED_KEYS: Final = frozenset(_STOP_OUTPUT_VALUE_TYPES)


def _unsupported_key_violations(*, keys: frozenset[str]) -> tuple[str, ...]:
    unsupported = sorted(keys - STOP_OUTPUT_ALLOWED_KEYS)
    violations = [
        f"unsupported top-level key {key!r}: the Codex CLI "
        f"{SUPPORTED_CODEX_CLI_VERSION} Stop-output schema sets additionalProperties: false"
        for key in unsupported
    ]
    if PRE_TOOL_USE_ONLY_KEY in unsupported:
        violations.append(
            f"{PRE_TOOL_USE_ONLY_KEY!r} is a PreToolUse-only field; a Stop hook that emits it "
            "is rejected by the Codex Stop runtime even though the JSON parses"
        )
    return tuple(violations)


def _value_type_violations(*, payload: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        f"top-level key {key!r} must be {_STOP_OUTPUT_VALUE_TYPES[key].__name__}, got "
        f"{type(payload[key]).__name__}"
        for key in sorted(payload)
        if key in _STOP_OUTPUT_VALUE_TYPES
        and not isinstance(payload[key], _STOP_OUTPUT_VALUE_TYPES[key])
    )


def validate_stop_output(*, output: str) -> Result[dict[str, object], tuple[str, ...]]:
    """Validate one NON-EMPTY Codex Stop-hook stdout payload against the closed schema.

    Empty stdout is how a Stop hook says "allow", so it carries no payload to
    validate and is reported as a violation here — callers filter it before
    reaching this seam. Every other rejection (unparseable JSON, a non-object
    top level, an out-of-schema key, a wrongly-typed value) rides the Failure
    rail carrying every violation found, so a caller reports the whole contract
    breach rather than the first one.
    """
    text = output.strip()
    if not text:
        return Failure(("stop output is empty; only non-empty hook stdout carries a payload",))
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as error:
        return Failure((f"stop output is not valid JSON: {error}",))
    if not isinstance(decoded, dict):
        return Failure(
            (f"top-level Stop output must be a JSON object, got {type(decoded).__name__}",)
        )
    payload = cast("dict[str, object]", decoded)
    violations = _unsupported_key_violations(keys=frozenset(payload)) + _value_type_violations(
        payload=payload
    )
    return Failure(violations) if violations else Success(payload)
