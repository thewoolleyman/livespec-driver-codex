"""Exercise the shipped Stop process against real session filesystem state."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "livespec/hooks/supervisor_completion_gate.py"

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-driver-codex-waq5mp
_CASES = (
    ("unidentified", False),
    ("owned", False),
    ("invalid-path", True),
    ("missing", True),
    ("legacy", True),
    ("terminal-without-producer", True),
    ("terminal-registered-producer", False),
    ("real-user-stop", False),
    ("reentry", False),
    ("canonical-blank", False),
    ("unexpected-evaluation-error", True),
    ("assistant-not-evidence", True),
    ("native-session-context", True),
)


@pytest.mark.parametrize(("case", "blocked"), _CASES)
def test_shipped_supervisor_topic_contract(tmp_path: Path, case: str, blocked: bool) -> None:
    """Each scenario crosses the real stdin/process/filesystem/stdout boundary."""
    (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")
    runtime = tmp_path / "tmp/overseer"
    foreign = runtime / "foreign/.supervisor-state"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("legacy foreign marker", encoding="utf-8")
    special_payloads: dict[str, dict[str, object]] = {
        "unidentified": {},
        "canonical-blank": {"supervisor_topic": "", "topic": "foreign"},
        "invalid-path": {"supervisor_topic": "../foreign"},
        "reentry": {"supervisor_topic": "owned", "stop_hook_active": True},
        "native-session-context": {},
    }
    payload = special_payloads.get(case, {"supervisor_topic": "owned"})
    env = {"PATH": os.environ.get("PATH", ""), "CLAUDE_PROJECT_DIR": str(tmp_path)}
    if case == "native-session-context":
        env["LIVESPEC_SUPERVISOR_TOPIC"] = "owned"
    elif case == "unexpected-evaluation-error":
        env["PATH"] = ""  # Missing git must fail closed for an identified session.
    elif case in ("real-user-stop", "assistant-not-evidence"):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "user" if case == "real-user-stop" else "assistant",
                    "message": {"content": "stop supervising owned"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        payload["transcript_path"] = str(transcript)
    if case in ("owned", "terminal-without-producer", "terminal-registered-producer", "legacy"):
        marker = runtime / "owned/.supervisor-state"
        marker.parent.mkdir()
        state = {
            "topic": "owned",
            "supervision_active": case != "owned",
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            "open_obligations": [],
            "completion_disposition": {"kind": "plan-complete", "question": None},
            "wake_producer": {
                "kind": "ledger",
                "identity": "ledger:owned",
                "registered_producer_identity": "ledger:owned",
                "cold_reentry": (
                    "cold-open tmp/overseer/owned/.supervisor-state and query fresh ledger"
                ),
            },
        }
        marker.write_text("legacy" if case == "legacy" else json.dumps(state), encoding="utf-8")
        if case == "terminal-registered-producer":
            (runtime / ".wake-producers.json").write_text(
                json.dumps({"registered_producer_identities": ["ledger:owned"]}),
                encoding="utf-8",
            )
    result = subprocess.run(
        [sys.executable, "-E", str(_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    if blocked:
        decision = json.loads(result.stdout)
        assert set(decision) == {"decision", "reason"}
        assert decision["decision"] == "block"
        assert "supervisor completion gate" in decision["reason"]
    else:
        assert result.stdout == ""
    assert foreign.read_text(encoding="utf-8") == "legacy foreign marker"


@pytest.mark.parametrize(
    ("overrides", "blocked"),
    [
        ({"topic": "foreign"}, True),
        ({"supervision_active": None}, True),
        ({"supervision_active": 0}, True),
        ({"updated_at": None}, True),
        ({"updated_at": "2026-01-01T00:00:00"}, True),
        ({"updated_at": "2000-01-01T00:00:00Z"}, True),
        ({"updated_at": "2999-01-01T00:00:00Z"}, True),
        ({"supervision_active": False, "updated_at": "stale"}, False),
        ({"open_obligations": ["verify the running repair"]}, True),
        ({"open_obligations": None}, True),
        ({"completion_disposition": {"kind": "none"}}, True),
        ({"completion_disposition": {"kind": "plan-complete", "question": "Done?"}}, True),
        (
            {"completion_disposition": {"kind": "maintainer-blocking", "question": "Proceed?"}},
            False,
        ),
        (
            {"completion_disposition": {"kind": "maintainer-blocking", "question": "A? B?"}},
            True,
        ),
        ({"wake_producer": None}, True),
    ],
)
def test_owned_marker_validation_over_real_stop_process(
    tmp_path: Path, overrides: dict[str, object], blocked: bool
) -> None:
    """Invalid owned evidence fails closed even beside a registered producer."""
    (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")
    runtime = tmp_path / "tmp/overseer"
    marker = runtime / "owned/.supervisor-state"
    marker.parent.mkdir(parents=True)
    state: dict[str, object] = {
        "topic": "owned",
        "supervision_active": True,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "open_obligations": [],
        "completion_disposition": {"kind": "plan-complete", "question": None},
        "wake_producer": {
            "kind": "ledger",
            "identity": "ledger:owned",
            "registered_producer_identity": "ledger:owned",
            "cold_reentry": "cold-open tmp/overseer/owned/.supervisor-state and query fresh ledger",
        },
    }
    state.update(overrides)
    original = json.dumps(state)
    marker.write_text(original, encoding="utf-8")
    (runtime / ".wake-producers.json").write_text(
        json.dumps({"registered_producer_identities": ["ledger:owned"]}), encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-E", str(_SCRIPT)],
        input=json.dumps({"supervisor_topic": "owned"}),
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", ""), "CLAUDE_PROJECT_DIR": str(tmp_path)},
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    if blocked:
        assert json.loads(result.stdout)["decision"] == "block"
    else:
        assert result.stdout == ""
    assert marker.read_text(encoding="utf-8") == original
