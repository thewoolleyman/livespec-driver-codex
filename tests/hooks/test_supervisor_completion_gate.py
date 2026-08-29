"""Tests for the Codex Stop hook that gates active overseer supervisors."""

from __future__ import annotations

import importlib
import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
_HOOK_SCRIPT = _HOOKS_DIR / "supervisor_completion_gate.py"
_HOOKS_JSON = _HOOKS_DIR / "hooks.json"
_PLUGIN_SOURCE = _REPO_ROOT / "livespec"
_PLUGIN_MANIFEST = _PLUGIN_SOURCE / ".codex-plugin" / "plugin.json"
_CODEX_STOP_ALLOWED_KEYS = {
    "continue",
    "decision",
    "reason",
    "stopReason",
    "suppressOutput",
    "systemMessage",
}


def _hook_module():
    assert _HOOK_SCRIPT.is_file(), "supervisor_completion_gate.py must be shipped"
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    sys.modules.pop("supervisor_completion_gate", None)
    return importlib.import_module("supervisor_completion_gate")


def _producer_module():
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    sys.modules.pop("_supervisor_producers", None)
    return importlib.import_module("_supervisor_producers")


def _project(*, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    root.joinpath(".livespec.jsonc").write_text(
        json.dumps({"implementation": {"plugin": "livespec-orchestrator-beads-fabro"}}),
        encoding="utf-8",
    )
    return root


def _payload(*, transcript_path: Path | None = None, topic: str | None = None) -> str:
    payload: dict[str, object] = {"stop_hook_active": False}
    if transcript_path is not None:
        payload["transcript_path"] = str(transcript_path)
    if topic is not None:
        payload["supervisor_topic"] = topic
    return json.dumps(payload)


def _transcript(*, root: Path, user_messages: list[str] | None = None) -> Path:
    entries = [
        {"type": "user", "message": {"content": [{"type": "text", "text": text}]}}
        for text in (user_messages or [])
    ]
    path = root / "transcript.jsonl"
    path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + ("\n" if entries else ""),
        encoding="utf-8",
    )
    return path


def _state_dir(*, root: Path, topic: str = "topic") -> Path:
    path = root / "tmp" / "overseer" / topic
    path.mkdir(parents=True, exist_ok=True)
    return path


def _updated_at(*, delta: timedelta = timedelta()) -> str:
    return (
        (datetime.now(tz=timezone.utc) + delta)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _base_state(*, topic: str = "topic") -> dict[str, object]:
    return {
        "supervision_active": True,
        "topic": topic,
        "updated_at": _updated_at(),
        "objective": "Watch the supervised plan.",
        "open_obligations": [],
        "completion_disposition": {"kind": "plan-complete", "question": None},
        "wake_producer": {
            "kind": "ledger",
            "live_pid": None,
            "expected_command": None,
            "identity": "ledger:topic",
            "registered_producer_identity": "ledger:topic",
            "cold_reentry": (
                "cold-open tmp/overseer/topic/.supervisor-state and re-query fresh ledger state"
            ),
        },
    }


def _write_state(*, root: Path, state: dict[str, object], topic: str = "topic") -> Path:
    path = _state_dir(root=root, topic=topic) / ".supervisor-state"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def _register_producer(*, root: Path, identity: str) -> None:
    registry = root / "tmp" / "overseer" / ".wake-producers.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"registered_producer_identities": [identity]}),
        encoding="utf-8",
    )


def _write_registry(*, root: Path, data: object, topic: str | None = None) -> None:
    base = root / "tmp" / "overseer"
    path = base / ".wake-producers.json" if topic is None else base / topic / ".wake-producers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _run_hook(
    *,
    root: Path,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
):
    hook = _hook_module()
    old_stdin = sys.stdin
    old_env = os.environ.copy()
    old_cwd = Path.cwd()
    stdout = io.StringIO()
    try:
        os.environ.clear()
        os.environ.update({"PATH": old_env.get("PATH", ""), **(env or {})})
        os.chdir(root)
        sys.stdin = io.StringIO(stdin if stdin is not None else _payload())
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(sys, "stdout", stdout)
            returncode = hook.main()
    finally:
        sys.stdin = old_stdin
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)
    return returncode, stdout.getvalue()


def _assert_blocks(*, output: str) -> str:
    assert output.strip(), "expected Stop hook to block"
    payload = json.loads(output)
    assert set(payload) <= _CODEX_STOP_ALLOWED_KEYS
    assert set(payload) == {"decision", "reason"}
    assert "hookSpecificOutput" not in payload
    assert payload["decision"] == "block"
    reason = payload["reason"]
    assert isinstance(reason, str)
    assert reason
    assert "supervisor completion gate" in reason
    return reason


def _assert_allows(*, output: str) -> None:
    assert output.strip() == ""


def test_hook_is_registered_for_codex_stop() -> None:
    declared = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["Stop"]
    commands = [hook["command"] for entry in declared for hook in entry["hooks"]]

    assert any("supervisor_completion_gate.py" in command for command in commands)


def test_known_supervisor_topic_without_marker_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)

    _, output = _run_hook(
        root=root,
        stdin=_payload(topic="topic"),
        env={"CLAUDE_PROJECT_DIR": str(root)},
    )

    reason = _assert_blocks(output=output)
    assert "missing marker" in reason


def test_empty_stdin_with_no_overseer_state_allows(tmp_path: Path) -> None:
    root = _project(root=tmp_path)

    _, output = _run_hook(root=root, stdin="", env={"CLAUDE_PROJECT_DIR": str(root)})

    _assert_allows(output=output)


def test_project_dir_can_be_found_from_cwd_without_env(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _register_producer(root=root, identity="ledger:topic")
    _write_state(root=root, state=_base_state())

    _, output = _run_hook(root=root)

    _assert_allows(output=output)


def test_stop_hook_reentry_and_non_object_payload_allow(tmp_path: Path) -> None:
    root = _project(root=tmp_path)

    _, reentry_output = _run_hook(
        root=root,
        stdin=json.dumps({"stop_hook_active": True, "supervisor_topic": "topic"}),
        env={"CLAUDE_PROJECT_DIR": str(root)},
    )
    _, list_output = _run_hook(root=root, stdin="[]", env={"CLAUDE_PROJECT_DIR": str(root)})

    _assert_allows(output=reentry_output)
    _assert_allows(output=list_output)


def test_no_livespec_project_allows(tmp_path: Path) -> None:
    _, output = _run_hook(root=tmp_path, stdin=_payload(topic="topic"))

    _assert_allows(output=output)


def test_malformed_marker_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _state_dir(root=root).joinpath(".supervisor-state").write_text("{not-json", encoding="utf-8")

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "malformed marker" in reason


def test_unreadable_and_non_object_markers_are_malformed(tmp_path: Path) -> None:
    hook = _hook_module()
    marker_dir = tmp_path / ".supervisor-state"
    marker_dir.mkdir()
    assert hook._read_marker(marker=marker_dir) == (None, "unreadable marker")
    marker = tmp_path / "marker"
    marker.write_text("[]", encoding="utf-8")
    assert hook._read_marker(marker=marker) == (None, "malformed marker")


def test_stale_marker_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["updated_at"] = _updated_at(delta=timedelta(days=-3))
    _register_producer(root=root, identity="ledger:topic")
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "stale marker" in reason


@pytest.mark.parametrize(
    ("updated_at", "expected"),
    [
        (None, "malformed marker timestamp"),
        ("not-a-date", "malformed marker timestamp"),
        ("2026-08-14T00:00:00", "malformed marker timestamp"),
        (_updated_at(delta=timedelta(minutes=10)), "stale marker timestamp"),
    ],
)
def test_malformed_or_future_marker_timestamps_block(
    tmp_path: Path,
    updated_at: object,
    expected: str,
) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["updated_at"] = updated_at
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert expected in reason


def test_open_obligations_block_even_with_terminal_disposition(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["open_obligations"] = ["verify the worker"]
    _register_producer(root=root, identity="ledger:topic")
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "open obligations" in reason


def test_malformed_obligations_block(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["open_obligations"] = "not-a-list"
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "malformed marker obligations" in reason


def test_malformed_obligations_and_disposition_block(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    obligations_state = _base_state()
    obligations_state["open_obligations"] = "not-a-list"
    _write_state(root=root, state=obligations_state, topic="obligations")
    disposition_state = _base_state(topic="disposition")
    disposition_state["completion_disposition"] = "not-a-dict"
    _write_state(root=root, state=disposition_state, topic="disposition")

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "malformed" in reason


def test_unknown_or_non_terminal_disposition_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["completion_disposition"] = {"kind": "none", "question": None}
    _register_producer(root=root, identity="ledger:topic")
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "non-terminal disposition" in reason


def test_unknown_disposition_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["completion_disposition"] = {"kind": "ready", "question": None}
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "unknown completion disposition" in reason


def test_plan_complete_with_registered_ledger_producer_allows(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _register_producer(root=root, identity="ledger:topic")
    _write_state(root=root, state=_base_state())

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    _assert_allows(output=output)


def test_inactive_supervisor_marker_allows(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["supervision_active"] = False
    state["open_obligations"] = ["ignored when inactive"]
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    _assert_allows(output=output)


def test_unregistered_forge_or_ledger_producer_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _write_state(root=root, state=_base_state())

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "unregistered wake producer" in reason


def test_registered_producer_registry_shapes_allow(tmp_path: Path) -> None:
    for index, registry in enumerate(
        [
            ["ledger:topic"],
            {"producers": [{"identity": "ledger:topic"}]},
            {"producers": ["ledger:topic"]},
            {"producers": {"ledger:topic": {"kind": "ledger"}}},
        ]
    ):
        root = _project(root=tmp_path / str(index))
        _write_registry(root=root, data=registry, topic="topic")
        _write_state(root=root, state=_base_state())

        _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

        _assert_allows(output=output)


def test_invalid_registry_shapes_do_not_authorize_producers(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _write_registry(root=root, data="ledger:topic")
    _write_state(root=root, state=_base_state())

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "unregistered wake producer" in reason


def test_registry_parser_ignores_entries_without_identity() -> None:
    producers = _producer_module()

    assert producers._ids_from_sequence(values=[{}, {"identity": ""}, " "]) == set()
    assert producers._ids_from_registry(data={"other": []}) == set()


def test_registered_producer_requires_registered_identity_field(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _register_producer(root=root, identity="ledger:topic")
    state = _base_state()
    producer = cast("dict[str, object]", state["wake_producer"])
    producer["registered_producer_identity"] = None
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "unregistered wake producer" in reason


def test_maintainer_blocking_requires_exactly_one_question(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _register_producer(root=root, identity="ledger:topic")
    state = _base_state()
    state["completion_disposition"] = {
        "kind": "maintainer-blocking",
        "question": "Should this supervised track wait for maintainer input?",
    }
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    _assert_allows(output=output)


def test_second_maintainer_question_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _register_producer(root=root, identity="ledger:topic")
    state = _base_state()
    state["completion_disposition"] = {
        "kind": "maintainer-blocking",
        "question": "Should we wait? Should we close?",
    }
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "exactly one maintainer question" in reason


def test_malformed_or_unknown_wake_producers_block(tmp_path: Path) -> None:
    for index, producer in enumerate([None, {"kind": "none"}, {"kind": "prose-claim"}]):
        root = _project(root=tmp_path / str(index))
        state = _base_state()
        state["wake_producer"] = producer
        _write_state(root=root, state=state)

        _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

        reason = _assert_blocks(output=output)
        assert "wake producer" in reason


def test_unknown_wake_producer_with_valid_cold_reentry_still_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["wake_producer"] = {
        "kind": "prose-claim",
        "live_pid": None,
        "expected_command": None,
        "identity": "claim",
        "registered_producer_identity": None,
        "cold_reentry": (
            "cold-open tmp/overseer/topic/.supervisor-state and re-query fresh ledger state"
        ),
    }
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "unknown wake producer" in reason


def test_local_producer_requires_complete_process_fields(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["wake_producer"] = {
        "kind": "pane-watcher",
        "live_pid": os.getpid(),
        "expected_command": None,
        "identity": "pytest",
        "registered_producer_identity": None,
        "cold_reentry": (
            "cold-open tmp/overseer/topic/.supervisor-state and re-query fresh ledger state"
        ),
    }
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "live_pid, expected_command, and identity" in reason


def test_local_producer_requires_live_process(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["wake_producer"] = {
        "kind": "pane-watcher",
        "live_pid": 999999999,
        "expected_command": "python",
        "identity": "wake-identity",
        "registered_producer_identity": None,
        "cold_reentry": (
            "cold-open tmp/overseer/topic/.supervisor-state and re-query fresh ledger state"
        ),
    }
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "pid is not live" in reason


def test_empty_process_cmdline_is_not_live(monkeypatch) -> None:
    producers = _producer_module()
    monkeypatch.setattr(Path, "read_bytes", lambda _path: b"")

    assert producers._process_command_line(pid=0) is None
    assert producers._process_command_line(pid=123) is None


def test_local_producer_requires_live_pid_expected_command_and_identity(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "wake-identity"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        state = _base_state()
        state["wake_producer"] = {
            "kind": "pane-watcher",
            "live_pid": proc.pid,
            "expected_command": "time.sleep",
            "identity": "wake-identity",
            "registered_producer_identity": None,
            "cold_reentry": (
                "cold-open tmp/overseer/topic/.supervisor-state and re-query fresh ledger state"
            ),
        }
        _write_state(root=root, state=state)

        _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})
    finally:
        try:
            proc.terminate()
        except PermissionError:
            # Some sandboxed CI runners deny cross-process signals even
            # within the same pid namespace; the child still exits on its
            # own once the test process (and its process group) ends.
            pass
        else:
            proc.wait(timeout=10)

    _assert_allows(output=output)


def test_local_producer_with_wrong_identity_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["wake_producer"] = {
        "kind": "overseer-daemon",
        "live_pid": os.getpid(),
        "expected_command": "definitely-not-this-command",
        "identity": "definitely-not-this-identity",
        "registered_producer_identity": None,
        "cold_reentry": (
            "cold-open tmp/overseer/topic/.supervisor-state and re-query fresh ledger state"
        ),
    }
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "wake producer process identity" in reason


def test_cold_reentry_must_name_marker_and_fresh_state(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _register_producer(root=root, identity="ledger:topic")
    state = _base_state()
    producer = cast("dict[str, object]", state["wake_producer"])
    producer["cold_reentry"] = "I promise to check later."
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "cold-open" in reason


def test_cold_reentry_must_requery_fresh_state(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _register_producer(root=root, identity="ledger:topic")
    state = _base_state()
    producer = cast("dict[str, object]", state["wake_producer"])
    producer["cold_reentry"] = "cold-open tmp/overseer/topic/.supervisor-state later"
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "fresh ledger/forge" in reason


def test_missing_cold_reentry_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    _register_producer(root=root, identity="ledger:topic")
    state = _base_state()
    producer = cast("dict[str, object]", state["wake_producer"])
    producer["cold_reentry"] = None
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "missing cold-open" in reason


def test_ordinary_user_message_is_additive_not_a_clear_signal(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    transcript = _transcript(root=root, user_messages=["thanks, you can finish for now"])
    state = _base_state()
    state["open_obligations"] = ["watch the active worker"]
    _write_state(root=root, state=state)

    _, output = _run_hook(
        root=root,
        stdin=_payload(transcript_path=transcript),
        env={"CLAUDE_PROJECT_DIR": str(root)},
    )

    reason = _assert_blocks(output=output)
    assert "open obligations" in reason


def test_missing_transcript_does_not_create_clear_signal(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["open_obligations"] = ["watch the active worker"]
    _write_state(root=root, state=state)

    _, output = _run_hook(
        root=root,
        stdin=_payload(transcript_path=root / "absent.jsonl"),
        env={"CLAUDE_PROJECT_DIR": str(root)},
    )

    reason = _assert_blocks(output=output)
    assert "open obligations" in reason


def test_malformed_transcript_does_not_create_clear_signal(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    transcript = root / "transcript.jsonl"
    transcript.write_text(
        "{bad-json\n[]\n" + json.dumps({"type": "user", "message": {"content": []}}) + "\n",
        encoding="utf-8",
    )
    state = _base_state()
    state["open_obligations"] = ["watch the active worker"]
    _write_state(root=root, state=state)

    _, output = _run_hook(
        root=root,
        stdin=_payload(transcript_path=transcript),
        env={"CLAUDE_PROJECT_DIR": str(root)},
    )

    reason = _assert_blocks(output=output)
    assert "open obligations" in reason


def test_user_text_parser_ignores_tool_result_and_malformed_entries() -> None:
    hook = _hook_module()
    assert hook._user_text(entry={"type": "assistant"}) is None
    assert hook._user_text(entry={"type": "user", "message": []}) is None
    assert hook._user_text(entry={"type": "user", "message": {"content": 123}}) is None
    assert hook._user_text(entry={"type": "user", "message": {"content": "  stop  "}}) == "stop"
    assert (
        hook._user_text(
            entry={
                "type": "user",
                "message": {"content": [{"type": "tool_result"}, {"type": "text", "text": "x"}]},
            }
        )
        is None
    )
    assert (
        hook._user_text(
            entry={
                "type": "user",
                "message": {
                    "content": [
                        "bad",
                        {"type": "other", "text": "ignored"},
                        {"type": "text", "text": 123},
                        {"type": "text", "text": "ok"},
                    ]
                },
            }
        )
        == "ok"
    )


def test_malformed_topic_blocks(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    state = _base_state()
    state["topic"] = ""
    _write_state(root=root, state=state)

    _, output = _run_hook(root=root, env={"CLAUDE_PROJECT_DIR": str(root)})

    reason = _assert_blocks(output=output)
    assert "malformed marker topic" in reason


def test_literal_stop_supervising_command_clears_at_driver_boundary(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    transcript = _transcript(root=root, user_messages=["stop supervising topic"])
    state = _base_state()
    state["open_obligations"] = ["watch the active worker"]
    _write_state(root=root, state=state)

    _, output = _run_hook(
        root=root,
        stdin=_payload(transcript_path=transcript),
        env={"CLAUDE_PROJECT_DIR": str(root)},
    )

    _assert_allows(output=output)


def test_replace_objective_command_is_not_a_clear_signal(tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    transcript = _transcript(root=root, user_messages=["replace supervision objective"])
    state = _base_state()
    state["open_obligations"] = ["watch the active worker"]
    _write_state(root=root, state=state)

    _, output = _run_hook(
        root=root,
        stdin=_payload(transcript_path=transcript),
        env={"CLAUDE_PROJECT_DIR": str(root)},
    )

    reason = _assert_blocks(output=output)
    assert "open obligations" in reason


def test_fail_closed_boundary_blocks_on_unexpected_exception(monkeypatch, tmp_path: Path) -> None:
    root = _project(root=tmp_path)
    hook = _hook_module()
    monkeypatch.setattr(hook, "_decision", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    stdout = io.StringIO()
    old_stdin = sys.stdin
    old_cwd = Path.cwd()
    try:
        os.chdir(root)
        sys.stdin = io.StringIO(_payload())
        monkeypatch.setattr(sys, "stdout", stdout)
        assert hook.main() == 0
    finally:
        os.chdir(old_cwd)
        sys.stdin = old_stdin

    reason = _assert_blocks(output=stdout.getvalue())
    assert "malformed marker or producer evidence" in reason


def test_installed_shape_blocks_active_marker_without_repo_imports(tmp_path: Path) -> None:
    assert _HOOK_SCRIPT.is_file(), "supervisor_completion_gate.py must be shipped"
    root = _project(root=tmp_path / "project")
    state = _base_state()
    state["open_obligations"] = ["still open"]
    _write_state(root=root, state=state)
    version = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))["version"]
    destination = tmp_path / "cache" / "livespec" / version
    shutil.copytree(_PLUGIN_SOURCE, destination, ignore=shutil.ignore_patterns("__pycache__"))

    result = subprocess.run(
        [sys.executable, "-E", str(destination / "hooks" / "supervisor_completion_gate.py")],
        input=_payload(),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(root),
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    reason = _assert_blocks(output=result.stdout)
    assert "open obligations" in reason
