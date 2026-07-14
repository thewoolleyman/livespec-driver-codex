"""Importable `main() -> int` contract tests for Driver-shipped hooks."""

from __future__ import annotations

import importlib
import io
import json
import sys
from pathlib import Path

__all__: list[str] = []

_HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


def _reload_hook(*, module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_block_auto_memory_main_returns_zero_without_raising(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    hook = _reload_hook(module_name="block_auto_memory")

    assert hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_codex_background_memory_audit_main_returns_zero_without_raising(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    hook = _reload_hook(module_name="codex_background_memory_audit")

    assert hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_livespec_footgun_guard_main_returns_zero_without_raising(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    hook = _reload_hook(module_name="livespec_footgun_guard")

    assert hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_no_shadow_ledger_import_is_side_effect_free_and_main_warns(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "message": {"content": [{"type": "text", "text": "write handoff"}]},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Write",
                                    "input": {
                                        "file_path": str(tmp_path / "HANDOFF.md"),
                                        "content": "- [ ] one\n- [ ] two\n- [x] three\n",
                                    },
                                }
                            ]
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"transcript_path": str(transcript), "stop_hook_active": False})),
    )

    hook = _reload_hook(module_name="no_shadow_ledger")

    assert hook.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert "no-shadow-ledger" in payload["systemMessage"]
