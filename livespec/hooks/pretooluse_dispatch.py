#!/usr/bin/env python3
"""One-process dispatcher for the Driver's Bash PreToolUse guards."""

from __future__ import annotations

import sys
from collections.abc import Callable

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


def main() -> int:
    """Evaluate every Bash guard in process and emit the first deny."""
    raw = sys.stdin.read()
    first_deny: str | None = None
    for guard in _GUARDS:
        decision = guard(raw=raw)
        if first_deny is None and decision is not None:
            first_deny = decision
    if first_deny is not None:
        _ = sys.stdout.write(first_deny + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
