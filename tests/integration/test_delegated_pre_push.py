"""Witnesses for the delegated pre-push gate wiring.

Covers SPECIFICATION/scenarios.md "a delegating host's push gates on the remote
executor and refuses on no verdict": the repository opts in through its
version-controlled configuration, the delegating path runs the client in place
of `just check` and cannot fall through to it, and a host holding no gates
credential runs the gate recipe locally and says so.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from livespec_dev_tooling import gate_remote_delegate

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "dev-tooling" / "check-pre-push.sh"

_FAKE_UV = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "$FAKE_LOG"
case "$*" in
  *green_token*) exit "${FAKE_TOKEN_RC:-1}" ;;
  *"gate_remote_delegate enabled"*) exit "${FAKE_ENABLED_RC:-1}" ;;
  *"gate_remote_delegate run"*) exit "${FAKE_RUN_RC:-0}" ;;
esac
exit 99
"""

_FAKE_JUST = """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "$FAKE_LOG"
exit "${FAKE_JUST_RC:-0}"
"""


def _run_pre_push(*, tmp_path: Path, token: int, enabled: int, run: int) -> tuple[int, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("uv", _FAKE_UV), ("just", _FAKE_JUST)):
        tool = bin_dir / name
        tool.write_text(body, encoding="utf-8")
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.log"
    log.touch()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "FAKE_TOKEN_RC": str(token),
        "FAKE_ENABLED_RC": str(enabled),
        "FAKE_RUN_RC": str(run),
    }
    done = subprocess.run(
        ["bash", str(_SCRIPT)], cwd=tmp_path, env=env, capture_output=True, text=True, check=False
    )
    return done.returncode, log.read_text(encoding="utf-8").splitlines()


def test_repository_config_opts_in_to_the_delegated_gate() -> None:
    assert gate_remote_delegate.delegated_gate_enabled(repo_root=_REPO_ROOT) is True


def test_delegating_host_runs_the_client_in_place_of_just_check(tmp_path: Path) -> None:
    rc, calls = _run_pre_push(tmp_path=tmp_path, token=1, enabled=0, run=0)

    assert rc == 0
    assert any("gate_remote_delegate run" in call for call in calls)
    assert not any(call.startswith("just") for call in calls)


def test_delegating_host_refuses_on_no_verdict_without_a_local_run(tmp_path: Path) -> None:
    rc, calls = _run_pre_push(tmp_path=tmp_path, token=1, enabled=0, run=1)

    assert rc == 1
    assert any("gate_remote_delegate run" in call for call in calls)
    assert not any(call.startswith("just") for call in calls)


def test_non_delegating_host_runs_just_check_locally(tmp_path: Path) -> None:
    rc, calls = _run_pre_push(tmp_path=tmp_path, token=1, enabled=1, run=0)

    assert rc == 0
    assert "just check" in calls
    assert not any("gate_remote_delegate run" in call for call in calls)


def test_green_token_match_skips_both_gates(tmp_path: Path) -> None:
    rc, calls = _run_pre_push(tmp_path=tmp_path, token=0, enabled=0, run=0)

    assert rc == 0
    assert not any("gate_remote_delegate" in call for call in calls)
    assert not any(call.startswith("just") for call in calls)


def test_host_without_the_gates_credential_gates_locally_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GATES_KUBECONFIG", str(tmp_path / "absent.kubeconfig"))
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])
    monkeypatch.chdir(_REPO_ROOT)

    rc = gate_remote_delegate.main()

    assert rc != 0
    assert gate_remote_delegate.GATED_LOCALLY in capsys.readouterr().err
