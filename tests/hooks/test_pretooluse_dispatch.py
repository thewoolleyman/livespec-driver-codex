"""Scenarios for the Bash PreToolUse guard dispatcher."""

from __future__ import annotations

import importlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOKS = _ROOT / "livespec" / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))


def _payload(*, command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _governed(*, root: Path) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps({"implementation": {"plugin": "livespec-orchestrator-beads-fabro"}}),
        encoding="utf-8",
    )


def _run_main(*, module: object, raw: str, monkeypatch: pytest.MonkeyPatch) -> str:
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    with redirect_stdout(output):
        assert module.main() == 0
    return output.getvalue()


def test_bash_registration_starts_only_the_dispatcher_process() -> None:
    """The Bash matcher has one Python command for all of its guards."""
    declared = json.loads((_HOOKS / "hooks.json").read_text(encoding="utf-8"))
    bash_entries = [
        entry for entry in declared["hooks"]["PreToolUse"] if entry.get("matcher") == "Bash"
    ]
    commands = [hook["command"] for entry in bash_entries for hook in entry["hooks"]]
    assert commands == ['python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_dispatch.py"']


def test_dispatcher_matches_every_standalone_bash_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A denial retains its standalone guard's output byte-for-byte."""
    dispatcher_path = _HOOKS / "pretooluse_dispatch.py"
    assert dispatcher_path.is_file()
    dispatcher = importlib.import_module("pretooluse_dispatch")
    footgun = importlib.import_module("livespec_footgun_guard")
    raw_bd = importlib.import_module("block_raw_bd_create")
    auto_memory = importlib.import_module("block_auto_memory")
    _governed(root=tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    cases = (
        (footgun, _payload(command="tmux kill-server")),
        (raw_bd, _payload(command="bd create -t dispatcher")),
        (auto_memory, _payload(command=f"echo x > {Path.home()}/.codex/memories/dispatcher.md")),
    )
    for guard, raw in cases:
        assert _run_main(module=dispatcher, raw=raw, monkeypatch=monkeypatch) == _run_main(
            module=guard, raw=raw, monkeypatch=monkeypatch
        )


def test_dispatcher_evaluates_every_guard_and_keeps_the_first_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A denial does not stop subsequent in-process guard evaluation."""
    dispatcher_path = _HOOKS / "pretooluse_dispatch.py"
    assert dispatcher_path.is_file()
    dispatcher = importlib.import_module("pretooluse_dispatch")
    calls: list[str] = []

    def allow(*, raw: str) -> str | None:
        del raw
        calls.append("allow")
        return None

    def first_deny(*, raw: str) -> str | None:
        del raw
        calls.append("first")
        return '{"guard":"first"}'

    def later_deny(*, raw: str) -> str | None:
        del raw
        calls.append("later")
        return '{"guard":"later"}'

    monkeypatch.setattr(dispatcher, "_GUARDS", (allow, first_deny, later_deny))
    assert _run_main(
        module=dispatcher, raw=_payload(command="git status"), monkeypatch=monkeypatch
    ) == ('{"guard":"first"}\n')
    assert calls == ["allow", "first", "later"]
