"""Tests for the one-process Bash PreToolUse guard dispatcher."""

from __future__ import annotations

import importlib
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOKS = _ROOT / "livespec" / "hooks"
_DISPATCHER = _HOOKS / "pretooluse_dispatch.py"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))


def _payload(*, command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _governed(*, root: Path) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps({"implementation": {"plugin": "livespec-orchestrator-beads-fabro"}}),
        encoding="utf-8",
    )


def _run_main(*, module: object, raw: str, monkeypatch: pytest.MonkeyPatch) -> str:
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    with redirect_stdout(output):
        assert module.main() == 0
    return output.getvalue()


def _run_standalone(*, script: str, raw: str, project_dir: Path) -> str:
    environment = {
        "HOME": str(Path.home()),
        "PATH": os.environ["PATH"],
        "CLAUDE_PROJECT_DIR": str(project_dir),
    }
    result = subprocess.run(
        ["python3", str(_HOOKS / script)],
        input=raw,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_dispatcher_preserves_each_standalone_deny_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every Bash guard keeps its standalone decision bytes through dispatch."""
    assert _DISPATCHER.is_file()
    dispatcher = importlib.import_module("pretooluse_dispatch")
    _governed(root=tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    cases = (
        ("livespec_footgun_guard.py", _payload(command="tmux kill-server")),
        ("block_raw_bd_create.py", _payload(command="bd create -t dispatcher")),
        (
            "block_auto_memory.py",
            _payload(command=f"echo x > {Path.home()}/.codex/memories/dispatcher.md"),
        ),
    )
    for script, raw in cases:
        assert _run_main(module=dispatcher, raw=raw, monkeypatch=monkeypatch) == _run_standalone(
            script=script, raw=raw, project_dir=tmp_path
        )


def test_dispatcher_evaluates_all_guards_and_keeps_the_first_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-process guard evaluation preserves dispatch order without early exit."""
    assert _DISPATCHER.is_file()
    dispatcher = importlib.import_module("pretooluse_dispatch")
    raw = _payload(command="git status --short")
    calls: list[str] = []

    def allow_one(*, raw: str) -> str | None:
        assert raw == _payload(command="git status --short")
        calls.append("one")
        return None

    def deny_two(*, raw: str) -> str | None:
        assert raw == _payload(command="git status --short")
        calls.append("two")
        return '{"guard":"two"}'

    def deny_three(*, raw: str) -> str | None:
        assert raw == _payload(command="git status --short")
        calls.append("three")
        return '{"guard":"three"}'

    monkeypatch.setattr(dispatcher, "_GUARDS", (allow_one, deny_two, deny_three))
    assert _run_main(module=dispatcher, raw=raw, monkeypatch=monkeypatch) == '{"guard":"two"}\n'
    assert calls == ["one", "two", "three"]
