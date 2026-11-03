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


def test_dispatcher_matches_every_standalone_bash_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A denial retains the first guard's exact standalone output bytes."""
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


def test_fail_open_guard_does_not_stop_the_remaining_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fail-open exception allows when no other guard has denied."""
    dispatcher = importlib.import_module("pretooluse_dispatch")
    raw = _payload(command="git status --short")
    calls: list[str] = []

    def broken(*, raw: str) -> str | None:
        del raw
        calls.append("broken")
        raise RuntimeError("fail open")

    def allowed(*, raw: str) -> str | None:
        del raw
        calls.append("allowed")
        return None

    monkeypatch.setattr(dispatcher, "_GUARDS", (broken, allowed))
    assert _run_main(module=dispatcher, raw=raw, monkeypatch=monkeypatch) == ""
    assert calls == ["broken", "allowed"]


def test_dispatcher_falls_back_after_an_outer_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """An earlier in-process deny survives fallback for the remaining guards."""
    dispatcher = importlib.import_module("pretooluse_dispatch")
    raw = _payload(command="git status --short")

    def first_deny(*, raw: str) -> str | None:
        del raw
        return '{"first":"deny"}'

    def outer_failure(*, guard, raw: str) -> str | None:
        del raw
        if guard is first_deny:
            return first_deny(raw="")
        raise RuntimeError("dispatcher failure")

    def second_guard(*, raw: str) -> str | None:
        del raw
        return None

    def no_fallback(*, raw: str, guards: tuple[object, ...]) -> None:
        del raw, guards
        return None

    monkeypatch.setattr(dispatcher, "_GUARDS", (first_deny, second_guard))
    monkeypatch.setattr(dispatcher, "_evaluate", outer_failure)
    monkeypatch.setattr(dispatcher, "_fallback", no_fallback)
    assert _run_main(module=dispatcher, raw=raw, monkeypatch=monkeypatch) == '{"first":"deny"}\n'
