#!/usr/bin/env python3
"""
block_raw_bd_create — PreToolUse hook denying a raw `bd create`.

Declared in hooks.json on the `Bash` tool. This hook inspects the command and
acts only when it identifies a raw `bd create`.

WHY THIS IS AN INTAKE FAILURE, not a style preference. A raw `bd create`
files the work-item at the beads-native status `open`, which is OUTSIDE the
runtime's livespec status vocabulary. The item therefore strands in backlog:
it never runs the intake Definition-of-Ready gate and never reaches the
factory.

Fail-open contract: ANY failure (malformed stdin, an unrecognizable payload) is
a silent pass-through with exit 0. The hook only denies when it POSITIVELY
identifies a raw create. `main()` owns stdin/stdout at the hook boundary,
catches every failure, and returns 0 on every path; it is importable (no work at
module import) so the body is testable in-process for real per-file coverage.

Self-contained by contract: the plugin installer ships this file under bare
system `python3` with no virtualenv and no third-party packages, so every
import here is the standard library or a sibling module shipped beside it.
"""

from __future__ import annotations

import json
import sys
from typing import cast

from _result import Failure, Result, Success

__all__: list[str] = []

_RAW_BD_CREATE = "bd create"


def _as_object_dict(*, value: object) -> dict[str, object] | None:
    """Narrow an arbitrary JSON value to a string-keyed dict, else None."""
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _is_raw_bd_create(*, command: str) -> bool:
    """True when the command runs `bd create`."""
    return _RAW_BD_CREATE in command


def _deny_reason() -> str:
    """The deny reason naming the intake failure a raw create produces."""
    return (
        "This project is livespec-governed. A raw `bd create` is NOT the intake "
        "path here: it files the work-item at the beads-native status `open`, "
        "OUTSIDE the runtime's livespec status vocabulary, so the item strands in "
        "backlog and never reaches the factory."
    )


def _deny_decision() -> str:
    reason = _deny_reason()
    return json.dumps(
        {
            "decision": "block",
            "reason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }
    )


def _decision(*, raw: str) -> str | None:
    """Return the deny-decision JSON, or None for a pass-through."""
    payload = _as_object_dict(value=json.loads(raw))
    if payload is None or payload.get("tool_name") != "Bash":
        return None
    tool_input = _as_object_dict(value=payload.get("tool_input"))
    if tool_input is None:
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    if not _is_raw_bd_create(command=command):
        return None
    return _deny_decision()


def _decision_result(*, raw: str) -> Result[str | None, Exception]:
    """Lift the expected malformed-payload failure from decision logic onto the rail.

    `ValueError` is raised by `json.loads`, including `JSONDecodeError`
    subclasses.
    """
    try:
        return Success(_decision(raw=raw))
    except ValueError as exc:
        return Failure(exc)


def main() -> int:
    """Hook entry point: emit the deny decision, if any; always exit 0.

    Owns the stdin read + stdout write at the hook boundary and catches every
    failure so the PreToolUse hook stays fail-open by contract — it only denies
    when it POSITIVELY identifies a raw create, and never exits non-zero.
    """
    try:
        decision = _decision_result(raw=sys.stdin.read()).value_or(default=None)
        if decision is not None:
            _ = sys.stdout.write(decision + "\n")
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
