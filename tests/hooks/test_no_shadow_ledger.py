"""Unit tests for `livespec/hooks/no_shadow_ledger.py`.

The hook is exercised exactly as the runtime runs it: as a subprocess,
with the Claude `Stop` hook input JSON on stdin
(`{"transcript_path": "...", "stop_hook_active": false}`) and a
`{"systemMessage": "..."}` WARNING payload (or empty stdout) read off
stdout. Codex consumes the Claude Stop hook I/O format, so this one body
serves both runtimes; the hook is WARN-only and fail-open, so it NEVER
emits a `decision` key and NEVER exits non-zero.

This body is shipped BYTE-IDENTICALLY by both Drivers
(livespec-driver-claude at `.claude-plugin/hooks/`, livespec-driver-codex
at `livespec/hooks/`); this test pins its contract.

Contract under test:

- WARN (a `{"systemMessage": ...}` payload on stdout, exit 0): the last
  turn wrote a PLANNING ARTIFACT — a `*handoff*.md`, or any `.md` under a
  `plan/` or `prompts/` directory — whose written content carries at
  least `CHECKBOX_THRESHOLD` (3) markdown checkbox task items
  (`- [ ]` / `- [x]`).
- SILENT (empty stdout, exit 0): a planning artifact below the checkbox
  threshold; checkbox-looking syntax that is inline prose
  (a backticked `` `[ ]` `` quoting the forbidden form) rather than a
  real list item; a write to a NON-planning path even with many
  checkboxes.
- FAIL-OPEN / SILENT (empty stdout, exit 0): malformed (non-JSON) stdin;
  `stop_hook_active` true (the hook's own re-entrancy guard); a transcript
  whose path does not exist.

Follows the family Python rules (keyword-only args via the leading `*`
separator, `from __future__ import annotations`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOK_SCRIPT = _REPO_ROOT / "livespec" / "hooks" / "no_shadow_ledger.py"
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import no_shadow_ledger  # noqa: E402 — path-dependent hook import.


@dataclass(frozen=True, kw_only=True)
class HookResult:
    returncode: int
    stdout: str
    stderr: str


def _assistant_write_entry(*, file_path: str, content: str) -> dict[str, object]:
    """A transcript assistant entry carrying one Write tool_use of `content`."""
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Write",
                    "input": {"file_path": file_path, "content": content},
                }
            ]
        },
    }


def _real_user_entry(*, text: str) -> dict[str, object]:
    """A transcript entry for a real (human-typed) user message."""
    return {
        "type": "user",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _write_transcript(*, root: Path, entries: list[dict[str, object]]) -> Path:
    """Write a JSONL transcript of `entries` and return its path."""
    transcript = root / "transcript.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )
    return transcript


def _stop_input(*, transcript_path: str, stop_hook_active: bool = False) -> str:
    return json.dumps({"transcript_path": transcript_path, "stop_hook_active": stop_hook_active})


def _run_hook(*, stdin: str) -> HookResult:
    old_stdin = sys.stdin
    stdout = StringIO()
    stderr = StringIO()
    try:
        sys.stdin = StringIO(stdin)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = no_shadow_ledger.main()
    finally:
        sys.stdin = old_stdin
    return HookResult(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def _run_hook_subprocess(*, stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(_HOOK_SCRIPT)],
        input=stdin,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _assert_warns(*, result: HookResult | subprocess.CompletedProcess[str]) -> str:
    """Assert the hook emitted a systemMessage warning and exited 0; return it."""
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "expected a systemMessage payload on stdout"
    payload = json.loads(result.stdout)
    message = payload["systemMessage"]
    assert isinstance(message, str), "systemMessage must be a string"
    assert message, "systemMessage must be non-empty"
    assert "no-shadow-ledger" in message
    # WARN-only contract: never a blocking decision.
    assert "decision" not in payload
    return message


def _assert_silent(*, result: HookResult | subprocess.CompletedProcess[str]) -> None:
    """Assert the hook passed through silently (empty stdout, exit 0)."""
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"expected silent pass-through; got {result.stdout!r}"


_THREE_CHECKBOXES = "# Handoff\n\n- [ ] step one\n- [ ] step two\n- [x] step three\n"


def test_hook_script_exists() -> None:
    assert _HOOK_SCRIPT.is_file()


# --------------------------------------------------------------------------
# WARN — a planning artifact with >= 3 checkbox task items
# --------------------------------------------------------------------------


def test_warns_on_handoff_with_three_checkboxes(tmp_path: Path) -> None:
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="please write a handoff"),
            _assistant_write_entry(
                file_path=str(tmp_path / "HANDOFF-session.md"),
                content=_THREE_CHECKBOXES,
            ),
        ],
    )
    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript)))
    message = _assert_warns(result=result)
    assert "HANDOFF-session.md" in message


def test_subprocess_smoke_warns_on_handoff_with_three_checkboxes(tmp_path: Path) -> None:
    """The shipped script path still speaks the Stop hook stdin/stdout protocol."""
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="please write a handoff"),
            _assistant_write_entry(
                file_path=str(tmp_path / "HANDOFF-session.md"),
                content=_THREE_CHECKBOXES,
            ),
        ],
    )
    result = _run_hook_subprocess(stdin=_stop_input(transcript_path=str(transcript)))
    _assert_warns(result=result)


def test_warns_on_plan_dir_markdown_with_checkboxes(tmp_path: Path) -> None:
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="draft the plan"),
            _assistant_write_entry(
                file_path=str(tmp_path / "plan" / "topic" / "design.md"),
                content=_THREE_CHECKBOXES,
            ),
        ],
    )
    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript)))
    _assert_warns(result=result)


def test_warns_on_prompts_dir_markdown_with_checkboxes(tmp_path: Path) -> None:
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="write the prompt"),
            _assistant_write_entry(
                file_path=str(tmp_path / "prompts" / "queue.md"),
                content=_THREE_CHECKBOXES,
            ),
        ],
    )
    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript)))
    _assert_warns(result=result)


# --------------------------------------------------------------------------
# SILENT — below threshold, inline-prose checkboxes, non-planning path
# --------------------------------------------------------------------------


def test_silent_on_handoff_below_threshold(tmp_path: Path) -> None:
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="please write a handoff"),
            _assistant_write_entry(
                file_path=str(tmp_path / "HANDOFF-session.md"),
                content="# Handoff\n\n- [ ] only one box\n\nNarrative prose follows.\n",
            ),
        ],
    )
    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript)))
    _assert_silent(result=result)


def test_silent_on_inline_prose_checkbox_syntax(tmp_path: Path) -> None:
    # A rule quoting the forbidden `[ ]` syntax inline (backticked, not a
    # list item) must NOT count — the line-anchored list-item regex skips it.
    prose = (
        "# Handoff\n\n"
        "The no-shadow-ledger rule forbids embedding a `[ ]` / `[x]` task "
        "queue in a handoff. Inline mentions like `[ ]` here, and `[x]` "
        "there, and another `[ ]` are prose, not a list.\n"
    )
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="please write a handoff"),
            _assistant_write_entry(
                file_path=str(tmp_path / "HANDOFF-session.md"),
                content=prose,
            ),
        ],
    )
    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript)))
    _assert_silent(result=result)


def test_silent_on_non_planning_path_with_checkboxes(tmp_path: Path) -> None:
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="update the readme"),
            _assistant_write_entry(
                file_path=str(tmp_path / "src" / "README.md"),
                content=_THREE_CHECKBOXES,
            ),
        ],
    )
    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript)))
    _assert_silent(result=result)


# --------------------------------------------------------------------------
# FAIL-OPEN / SILENT — malformed stdin, stop_hook_active, missing transcript
# --------------------------------------------------------------------------


def test_fail_open_non_json_stdin() -> None:
    result = _run_hook(stdin="not json at all")
    _assert_silent(result=result)


def test_fail_open_empty_stdin() -> None:
    result = _run_hook(stdin="")
    _assert_silent(result=result)


def test_silent_when_stop_hook_active(tmp_path: Path) -> None:
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="please write a handoff"),
            _assistant_write_entry(
                file_path=str(tmp_path / "HANDOFF-session.md"),
                content=_THREE_CHECKBOXES,
            ),
        ],
    )
    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript), stop_hook_active=True))
    _assert_silent(result=result)


def test_silent_when_transcript_missing(tmp_path: Path) -> None:
    result = _run_hook(stdin=_stop_input(transcript_path=str(tmp_path / "does-not-exist.jsonl")))
    _assert_silent(result=result)


def test_fail_open_when_transcript_read_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transcript = _write_transcript(
        root=tmp_path,
        entries=[
            _real_user_entry(text="please write a handoff"),
            _assistant_write_entry(
                file_path=str(tmp_path / "HANDOFF-session.md"),
                content=_THREE_CHECKBOXES,
            ),
        ],
    )

    def broken_read_text(self: Path, *, encoding: str | None = None) -> str:
        _ = self
        _ = encoding
        raise OSError("unreadable transcript")

    monkeypatch.setattr(no_shadow_ledger.Path, "read_text", broken_read_text)

    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript)))
    _assert_silent(result=result)


def test_real_user_entry_variants() -> None:
    assert no_shadow_ledger._is_real_user_entry(entry={"type": "assistant"}) is False
    assert no_shadow_ledger._is_real_user_entry(entry={"type": "user", "message": []}) is False
    assert (
        no_shadow_ledger._is_real_user_entry(
            entry={"type": "user", "message": {"content": "hello"}}
        )
        is True
    )
    assert (
        no_shadow_ledger._is_real_user_entry(entry={"type": "user", "message": {"content": ""}})
        is False
    )
    assert (
        no_shadow_ledger._is_real_user_entry(entry={"type": "user", "message": {"content": 123}})
        is False
    )
    assert (
        no_shadow_ledger._is_real_user_entry(
            entry={"type": "user", "message": {"content": [{"type": "tool_result"}]}}
        )
        is False
    )
    assert (
        no_shadow_ledger._is_real_user_entry(
            entry={"type": "user", "message": {"content": ["not a block"]}}
        )
        is False
    )
    assert (
        no_shadow_ledger._is_real_user_entry(
            entry={"type": "user", "message": {"content": [{"type": "image"}]}}
        )
        is False
    )


def test_written_text_variants() -> None:
    assert no_shadow_ledger._written_text(name="Write", tool_input={"content": 123}) == ""
    assert no_shadow_ledger._written_text(name="Edit", tool_input={"new_string": "new"}) == "new"
    assert no_shadow_ledger._written_text(name="Edit", tool_input={"new_string": 123}) == ""
    assert (
        no_shadow_ledger._written_text(
            name="MultiEdit",
            tool_input={"edits": [{"new_string": "a"}, {"new_string": 3}, "bad"]},
        )
        == "a"
    )
    assert no_shadow_ledger._written_text(name="MultiEdit", tool_input={"edits": "bad"}) == ""
    assert no_shadow_ledger._written_text(name="Other", tool_input={}) == ""


def test_last_turn_writes_skips_non_persisting_shapes() -> None:
    entries = [
        {"type": "system", "message": {"content": []}},
        {"type": "assistant", "message": []},
        {"type": "assistant", "message": {"content": "bad"}},
        {"type": "assistant", "message": {"content": ["bad block"]}},
        {"type": "assistant", "message": {"content": [{"type": "text"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}},
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Write", "input": []}]},
        },
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Write", "input": {"file_path": ""}}]
            },
        },
        _assistant_write_entry(file_path="plan/handoff.md", content="ok"),
    ]
    assert no_shadow_ledger._last_turn_writes(entries=entries) == [("plan/handoff.md", "ok")]


def test_planning_artifact_non_markdown_is_false() -> None:
    assert no_shadow_ledger._is_planning_artifact(path="plan/notes.txt") is False
    assert no_shadow_ledger._is_planning_artifact(path="src/readme.md") is False


def test_warning_skips_blank_malformed_and_non_mapping_transcript_lines(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\nnot json\n[]\n"
        + json.dumps(_assistant_write_entry(file_path="plan/queue.md", content=_THREE_CHECKBOXES))
        + "\n",
        encoding="utf-8",
    )
    result = _run_hook(stdin=_stop_input(transcript_path=str(transcript)))
    _assert_warns(result=result)


def test_silent_on_non_mapping_stop_payload() -> None:
    result = _run_hook(stdin="[]")
    _assert_silent(result=result)


def test_silent_on_missing_transcript_path_key() -> None:
    result = _run_hook(stdin=json.dumps({}))
    _assert_silent(result=result)
