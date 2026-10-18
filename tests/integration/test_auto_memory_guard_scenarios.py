"""Integration coverage for the auto-memory guard scenario in scenarios.md.

The plugin-shipped PreToolUse auto-memory guard is driven exactly as Codex
runs it: the hook-input JSON on stdin, the
`hookSpecificOutput.permissionDecision` payload read off stdout. These
tests witness `## Scenario: auto-memory guard refuses every write route
into an agent memory directory` — that in a governed project a write into
either agent memory directory is DENIED on every route (Write, Edit,
apply_patch, and a shell write) with one identical reason routing durable
guidance to a short AGENTS.md entry pointing at a `.ai/<topic>.md` file,
and that a shell command which only reads a memory directory, or removes a
note with `rm`, is NOT denied. They live at the integration tier because a
scenario describes the guard's runtime hook I/O behavior, not a pure
helper.
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

import block_auto_memory  # noqa: E402 — path-dependent plugin-hook import.

_CODEX_MEMORIES = Path.home() / ".codex" / "memories"
_CLAUDE_MEMORY = Path.home() / ".claude" / "projects" / "-data-projects-demo" / "memory"


def _governed_project(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".livespec.jsonc").write_text(
        '{"implementation": {"plugin": "demo-orchestrator"}}', encoding="utf-8"
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))


def _run_guard(*, stdin: str) -> tuple[int, str]:
    old_stdin = sys.stdin
    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdin = io.StringIO(stdin)
        sys.stdout = captured
        rc = block_auto_memory.main()
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout
    return rc, captured.getvalue()


def _hook_input(*, tool_name: str, tool_input: dict[str, str]) -> str:
    return json.dumps({"tool_name": tool_name, "tool_input": tool_input})


def _deny_reason(*, stdin: str) -> str:
    rc, out = _run_guard(stdin=stdin)
    assert rc == 0, out
    assert out.strip(), "expected a decision payload on stdout"
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert isinstance(reason, str)
    return reason


_WRITE_ROUTES = [
    _hook_input(tool_name="Write", tool_input={"file_path": f"{_CODEX_MEMORIES}/a.md"}),
    _hook_input(tool_name="Edit", tool_input={"file_path": f"{_CLAUDE_MEMORY}/user_role.md"}),
    _hook_input(
        tool_name="apply_patch",
        tool_input={
            "input": f"*** Begin Patch\n*** Add File: {_CODEX_MEMORIES}/n.md\n+x\n*** End Patch\n"
        },
    ),
    _hook_input(tool_name="Bash", tool_input={"command": f"echo note > {_CODEX_MEMORIES}/a.md"}),
    _hook_input(tool_name="Bash", tool_input={"command": f"echo note | tee {_CLAUDE_MEMORY}/a.md"}),
    _hook_input(tool_name="Bash", tool_input={"command": f"sed -i s/a/b/ {_CLAUDE_MEMORY}/a.md"}),
    _hook_input(tool_name="Bash", tool_input={"command": f"cp notes.md {_CODEX_MEMORIES}/"}),
    _hook_input(
        tool_name="Bash",
        tool_input={"command": f"python3 -c \"open('{_CLAUDE_MEMORY}/a.md', 'w').write('x')\""},
    ),
]
_WRITE_ROUTE_IDS = [
    "write-codex-store",
    "edit-claude-layout",
    "apply-patch-codex-store",
    "shell-redirect",
    "shell-tee",
    "shell-sed-i",
    "shell-cp",
    "shell-inline-python",
]


@pytest.mark.parametrize("stdin", _WRITE_ROUTES, ids=_WRITE_ROUTE_IDS)
def test_auto_memory_guard_refuses_every_write_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdin: str
) -> None:
    _governed_project(tmp_path=tmp_path, monkeypatch=monkeypatch)
    reference = _deny_reason(stdin=_WRITE_ROUTES[0])
    reason = _deny_reason(stdin=stdin)
    assert reason == reference
    assert "AGENTS.md" in reason
    assert ".ai/<topic>.md" in reason


@pytest.mark.parametrize(
    "command",
    [
        f"cat {_CODEX_MEMORIES}/a.md",
        f"ls {_CLAUDE_MEMORY}",
        f"grep -r note {_CLAUDE_MEMORY}",
        f"rm {_CLAUDE_MEMORY}/a.md",
    ],
    ids=["cat", "ls", "grep", "rm"],
)
def test_auto_memory_guard_lets_reads_and_rm_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    _governed_project(tmp_path=tmp_path, monkeypatch=monkeypatch)
    rc, out = _run_guard(stdin=_hook_input(tool_name="Bash", tool_input={"command": command}))
    assert rc == 0, out
    assert out.strip() == "", f"expected pass-through, got {out!r}"
