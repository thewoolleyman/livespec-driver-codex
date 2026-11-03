"""Process-readiness support for hook tests that inspect a child's argv."""

from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

import pytest

__all__ = ["wait_for_process_command_line"]


def wait_for_process_command_line(
    *,
    pid: int,
    expected_command: str,
    identity: str,
    timeout_seconds: float = 10,
) -> None:
    """Wait for a child to exec the argv the completion-gate fixture requires."""
    deadline = monotonic() + timeout_seconds
    command_line_path = Path("/proc") / str(pid) / "cmdline"
    while monotonic() < deadline:
        try:
            command_line = (
                command_line_path.read_bytes().replace(b"\x00", b" ").decode(errors="replace")
            )
        except OSError:
            command_line = ""
        if expected_command in command_line and identity in command_line:
            return
        sleep(0.01)
    pytest.fail("spawned wake producer did not exec the expected command before deadline")
