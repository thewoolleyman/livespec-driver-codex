"""Tests for the versioned Codex Stop-output contract helper.

The negative path is the point: `test_injected_pre_tool_use_output_is_rejected`
feeds the helper the exact shape that shipped — an otherwise well-formed Stop
block payload carrying a PreToolUse `hookSpecificOutput` object — and requires a
rejection. A helper that only asserted parseability would pass that payload,
which is how the incident reached a release.
"""

from __future__ import annotations

import json

import pytest
from returns.result import Failure, Success

from .codex_stop_output_contract import (
    PRE_TOOL_USE_ONLY_KEY,
    STOP_OUTPUT_ALLOWED_KEYS,
    SUPPORTED_CODEX_CLI_VERSION,
    SUPPORTED_SCHEMA_PROVENANCE,
    validate_stop_output,
)

__all__: list[str] = []

_BLOCK_REASON = (
    "livespec supervisor completion gate: continuing the session because "
    "open obligations remain."
)


def _violations(*, output: str) -> tuple[str, ...]:
    result = validate_stop_output(output=output)
    assert isinstance(result, Failure), f"expected a rejection, got {result!r}"
    return result.failure()


def test_helper_records_the_supported_cli_schema_provenance() -> None:
    assert SUPPORTED_CODEX_CLI_VERSION == "0.150.1"
    assert SUPPORTED_CODEX_CLI_VERSION in SUPPORTED_SCHEMA_PROVENANCE
    assert "additionalProperties: false" in SUPPORTED_SCHEMA_PROVENANCE
    assert "codex-stop-hook-schema-release-gate" in SUPPORTED_SCHEMA_PROVENANCE


def test_allowed_key_set_is_the_closed_codex_stop_top_level_schema() -> None:
    assert sorted(STOP_OUTPUT_ALLOWED_KEYS) == [
        "continue",
        "decision",
        "reason",
        "stopReason",
        "suppressOutput",
        "systemMessage",
    ]
    assert PRE_TOOL_USE_ONLY_KEY not in STOP_OUTPUT_ALLOWED_KEYS


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"decision": "block", "reason": _BLOCK_REASON},
        {"systemMessage": "livespec supervisor completion gate: marker refreshed."},
        {"continue": False, "stopReason": "supervision complete", "suppressOutput": True},
        {
            "continue": True,
            "decision": "block",
            "reason": _BLOCK_REASON,
            "stopReason": "open obligations remain",
            "suppressOutput": False,
            "systemMessage": "see tmp/overseer/topic/.supervisor-state",
        },
    ],
)
def test_representative_valid_stop_payloads_pass(payload: dict[str, object]) -> None:
    result = validate_stop_output(output=json.dumps(payload) + "\n")

    assert result == Success(payload)


def test_injected_pre_tool_use_output_is_rejected() -> None:
    """The shipped defect: valid JSON, valid Stop keys, plus a PreToolUse field."""
    injected = json.dumps(
        {
            "decision": "block",
            "reason": _BLOCK_REASON,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": _BLOCK_REASON,
            },
        }
    )

    violations = _violations(output=injected)

    assert any("hookSpecificOutput" in violation for violation in violations)
    assert any("PreToolUse-only" in violation for violation in violations)
    assert any("additionalProperties: false" in violation for violation in violations)


def test_pre_tool_use_only_payload_is_rejected() -> None:
    violations = _violations(
        output=json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}}
        )
    )

    assert any("PreToolUse-only" in violation for violation in violations)


def test_every_out_of_schema_key_is_reported() -> None:
    violations = _violations(output=json.dumps({"decision": "block", "extra": 1, "another": 2}))

    assert any("'another'" in violation for violation in violations)
    assert any("'extra'" in violation for violation in violations)


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("", "stop output is empty"),
        ("   \n", "stop output is empty"),
        ("{not-json", "not valid JSON"),
        ("[]", "must be a JSON object, got list"),
        ('"block"', "must be a JSON object, got str"),
    ],
)
def test_unparseable_or_non_object_outputs_are_rejected(output: str, expected: str) -> None:
    violations = _violations(output=output)

    assert any(expected in violation for violation in violations)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"decision": True}, "'decision' must be str, got bool"),
        ({"reason": None}, "'reason' must be str, got NoneType"),
        ({"continue": "false"}, "'continue' must be bool, got str"),
        ({"suppressOutput": 1}, "'suppressOutput' must be bool, got int"),
        ({"stopReason": []}, "'stopReason' must be str, got list"),
        ({"systemMessage": {}}, "'systemMessage' must be str, got dict"),
    ],
)
def test_wrongly_typed_values_are_rejected(payload: dict[str, object], expected: str) -> None:
    violations = _violations(output=json.dumps(payload))

    assert any(expected in violation for violation in violations)
