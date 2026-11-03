#!/usr/bin/env python3
"""One-process dispatcher for the Driver's Bash PreToolUse guards."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from subprocess import run

import block_auto_memory
import block_raw_bd_create
import livespec_footgun_guard

__all__: list[str] = []

Guard = Callable[..., str | None]
_GUARDS: tuple[Guard, ...] = (
    livespec_footgun_guard.evaluate,
    block_raw_bd_create.evaluate,
    block_auto_memory.evaluate,
)
_SCRIPTS = ("livespec_footgun_guard.py", "block_raw_bd_create.py", "block_auto_memory.py")


def _evaluate(*, guard: Guard, raw: str) -> str | None:
    """Discharge one guard's own failure posture without stopping its peers."""
    try:
        return guard(raw=raw)
    except Exception:  # noqa: BLE001 — unknown guard failures are fail-open
        return None


def _fallback(*, raw: str, guards: tuple[Guard, ...]) -> str | None:
    """Run guards the dispatcher could not reach through their standalone boundary."""
    for guard in guards:
        index = _GUARDS.index(guard)
        result = run(
            [sys.executable, str(Path(__file__).with_name(_SCRIPTS[index]))],
            input=raw,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.rstrip("\n")
    return None


def main() -> int:
    """Run every registered guard and emit the first deny in dispatch order."""
    raw = sys.stdin.read()
    first_deny: str | None = None
    for index, guard in enumerate(_GUARDS):
        try:
            decision = _evaluate(guard=guard, raw=raw)
        except Exception:  # noqa: BLE001 — dispatcher failure invokes standalone guards
            fallback = _fallback(raw=raw, guards=_GUARDS[index:])
            if first_deny is None:
                first_deny = fallback
            break
        if first_deny is None and decision is not None:
            first_deny = decision
    if first_deny is not None:
        _ = sys.stdout.write(first_deny + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
