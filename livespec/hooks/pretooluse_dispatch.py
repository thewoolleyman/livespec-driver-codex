#!/usr/bin/env python3
"""One-process dispatcher for the Driver's Bash PreToolUse guards."""

from __future__ import annotations

import sys
from collections.abc import Callable

__all__: list[str] = []

Guard = Callable[..., str | None]
_GUARDS: tuple[Guard, ...] = ()


def main() -> int:
    """Run every registered guard and emit the first deny in dispatch order."""
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
