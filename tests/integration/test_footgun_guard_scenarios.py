"""Integration coverage for the footgun-guard scenarios in scenarios.md.

The plugin-shipped PreToolUse footgun guard is driven exactly as Codex
runs it: the hook-input JSON on stdin, the
`hookSpecificOutput.permissionDecision` payload read off stdout. These
tests witness the two guard scenarios in SPECIFICATION/scenarios.md —
that a never-legitimate command is DENIED, and that the same dangerous
string appearing as DATA (plus empty / non-JSON / non-Bash stdin) FAILS
OPEN with no deny decision and exit 0. They live at the integration tier
because a scenario describes the guard's runtime hook I/O behavior, not a
pure helper.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import livespec_footgun_guard  # noqa: E402 — path-dependent plugin-hook import.


def _run_guard(*, stdin: str) -> tuple[int, str]:
    old_stdin = sys.stdin
    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdin = io.StringIO(stdin)
        sys.stdout = captured
        rc = livespec_footgun_guard.main()
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout
    return rc, captured.getvalue()


def _bash_input(*, command: str, tool_name: str = "Bash") -> str:
    return json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})


def test_footgun_guard_denies_a_never_legitimate_command() -> None:
    rc, out = _run_guard(stdin=_bash_input(command="git commit --no-verify -m wip"))
    assert rc == 0, out
    assert out.strip(), "expected a decision payload on stdout"
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "--no-verify" in decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    "stdin",
    [
        _bash_input(command='echo "never use --no-verify"'),
        _bash_input(command="git config --get core.bare"),
        "",
        "this is not json",
        _bash_input(command="git commit --no-verify -m wip", tool_name="Edit"),
    ],
    ids=[
        "no-verify-as-echo-data",
        "core-bare-read",
        "empty-stdin",
        "non-json-stdin",
        "non-bash-tool",
    ],
)
def test_footgun_guard_fails_open_on_the_dangerous_string_as_data(stdin: str) -> None:
    rc, out = _run_guard(stdin=stdin)
    assert rc == 0, out
    assert out.strip() == "", f"expected silent fail-open pass-through; got {out!r}"


def test_footgun_guard_denies_a_file_write_at_a_primary_checkout(tmp_path: Path) -> None:
    """Witness scenarios.md "commit at the primary checkout is refused".

    The guard's fast early-warning arm denies a shell edit that would WRITE
    FILES at a livespec PRIMARY checkout (a repo whose
    `git config --get livespec.primaryPath` equals its own worktree root),
    directing the contributor to a worktree. The control arm is the sibling
    fail-open suite above: the same shell-edit machinery passes silently when
    the target is not a primary checkout.
    """
    import subprocess

    def _git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    _git("init")
    _git("config", "livespec.primaryPath", str(tmp_path))
    target = tmp_path / "tracked.txt"

    rc, out = _run_guard(stdin=_bash_input(command=f"echo x > {target}"))
    assert rc == 0, out
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "worktree" in decision["permissionDecisionReason"].lower()
