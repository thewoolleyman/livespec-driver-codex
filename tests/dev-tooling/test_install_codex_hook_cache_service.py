"""macOS provisioning tests; no test touches the host's service manager."""

from __future__ import annotations

import importlib.util
import json
import plistlib
import subprocess
import time
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "dev-tooling"
if not SOURCE.is_dir():
    SOURCE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "install_codex_hook_cache_service", SOURCE / "install_codex_hook_cache_service.py"
)
assert SPEC is not None
assert SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def desired(home: Path) -> dict:
    """Paths with spaces and shell metacharacters remain a single argv entry."""
    return installer.definition(
        driver_root=home / "workspace" / "Driver with spaces;echo nope",
        codex_home=home / "Codex home",
        interpreter=Path("/opt/homebrew/bin/python3"),
        home=home,
    )


def heartbeat(home: Path, *, pid: int = 5011, age: float = 0, error=None) -> None:
    path = home / ".local/state/livespec-driver-codex/observer.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"pid": pid, "heartbeat_epoch": time.time() - age, "last_error": error})
    )


def test_launch_agent_retains_stable_paths_and_restarts_after_login_or_exit(tmp_path: Path) -> None:
    definition = plistlib.loads(plistlib.dumps(desired(tmp_path)))
    assert definition["ProgramArguments"][0] == "/opt/homebrew/bin/python3"
    assert definition["ProgramArguments"][1].endswith(
        "Driver with spaces;echo nope/dev-tooling/codex_hook_cache_observe.py"
    )
    assert definition["ProgramArguments"][-1] == str(tmp_path / "Codex home")
    assert definition["RunAtLoad"] is True
    assert definition["KeepAlive"] is True
    assert definition["ThrottleInterval"] >= 10
    assert definition["EnvironmentVariables"] == {"LIVESPEC_CODEX_HOOK_CACHE_SUPERVISOR": "launchd"}


def test_check_reports_missing_service_without_creating_files(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 113, stdout="", stderr="not found")

    monkeypatch.setattr(installer.subprocess, "run", run)
    assert (
        installer.converge(desired=desired(tmp_path), home=tmp_path, uid=501, check_only=True) == 1
    )
    assert calls == [["launchctl", "print", f"gui/501/{installer.LABEL}"]]
    assert not (tmp_path / "Library").exists()


def test_install_is_idempotent_and_detects_loaded_but_crashing_job(
    tmp_path: Path, monkeypatch
) -> None:
    calls = []
    loaded = False

    def run(argv, **_kwargs):
        nonlocal loaded
        calls.append(argv)
        if argv[1] == "bootstrap":
            loaded = True
            heartbeat(tmp_path)
        return subprocess.CompletedProcess(
            argv,
            0 if loaded else 113,
            stdout="state = running\npid = 5011" if loaded else "",
            stderr="",
        )

    monkeypatch.setattr(installer.subprocess, "run", run)
    definition = desired(tmp_path)
    assert installer.converge(desired=definition, home=tmp_path, uid=501, check_only=False) == 0
    path = tmp_path / "Library" / "LaunchAgents" / f"{installer.LABEL}.plist"
    assert plistlib.loads(path.read_bytes()) == definition
    assert path.stat().st_mode & 0o777 == 0o600
    previous = path.stat().st_mtime_ns
    calls.clear()
    assert installer.converge(desired=definition, home=tmp_path, uid=501, check_only=False) == 0
    assert calls[0] == ["launchctl", "print", f"gui/501/{installer.LABEL}"]
    assert calls[1][2] == "status"
    assert len(calls) == 2
    assert path.stat().st_mtime_ns == previous

    def crashed(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="state = waiting\nlast exit code = 127")

    monkeypatch.setattr(installer.subprocess, "run", crashed)
    assert installer.converge(desired=definition, home=tmp_path, uid=501, check_only=True) == 1


def test_changed_definition_restarts_only_the_owned_job(tmp_path: Path, monkeypatch) -> None:
    calls = []
    path = tmp_path / "Library" / "LaunchAgents" / f"{installer.LABEL}.plist"
    path.parent.mkdir(parents=True)
    path.write_bytes(plistlib.dumps({"Label": installer.LABEL, "ProgramArguments": ["old"]}))
    heartbeat(tmp_path)

    def run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="state = running\npid = 5011", stderr="")

    monkeypatch.setattr(installer.subprocess, "run", run)
    assert (
        installer.converge(desired=desired(tmp_path), home=tmp_path, uid=501, check_only=False) == 0
    )
    assert calls[2] == ["launchctl", "bootout", f"gui/501/{installer.LABEL}"]
    assert calls[3] == ["launchctl", "bootstrap", "gui/501", str(path)]


def test_a_failed_bootstrap_is_not_reported_as_success(tmp_path: Path, monkeypatch) -> None:
    def run(argv, **_kwargs):
        if argv[1] == "bootstrap":
            raise subprocess.CalledProcessError(5, argv)
        return subprocess.CompletedProcess(argv, 113, stdout="", stderr="")

    monkeypatch.setattr(installer.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        installer.converge(desired=desired(tmp_path), home=tmp_path, uid=501, check_only=False)


def test_a_cache_or_worktree_source_is_rejected(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "plugins" / "cache"
    with pytest.raises(ValueError, match="managed plugin cache"):
        installer.validate_source(
            driver_root=cache / "driver", codex_home=tmp_path, interpreter=Path("python3")
        )

    def run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=".git/worktrees/feature\n.git\n")

    monkeypatch.setattr(installer.subprocess, "run", run)
    with pytest.raises(ValueError, match="durable primary checkout"):
        installer.validate_source(
            driver_root=tmp_path / "feature", codex_home=tmp_path, interpreter=Path("python3")
        )


def test_a_live_detached_record_refuses_install_without_killing_it(
    tmp_path: Path, monkeypatch
) -> None:
    heartbeat(tmp_path, pid=12345)
    signals = []

    def probe(pid, sig):
        signals.append((pid, sig))

    def run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 113, stdout="", stderr="not found")

    monkeypatch.setattr(installer.os, "kill", probe)
    monkeypatch.setattr(installer.subprocess, "run", run)
    with pytest.raises(ValueError, match="live unmanaged pid 12345"):
        installer.converge(desired=desired(tmp_path), home=tmp_path, uid=501, check_only=False)
    assert signals == [(12345, 0)]
    assert not (tmp_path / "Library").exists()


def test_install_refuses_a_crashing_job_even_when_bootstrap_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    def run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="state = waiting\nlast exit code = 127")

    ticks = iter([0, 1, 16])
    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(installer.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="own healthy observer heartbeat"):
        installer.converge(desired=desired(tmp_path), home=tmp_path, uid=501, check_only=False)


@pytest.mark.parametrize(
    ("pid", "age", "error"), [(99, 0, None), (5011, 61, None), (5011, 0, "broken")]
)
def test_only_a_fresh_healthy_launchd_owned_heartbeat_counts(
    tmp_path: Path, pid: int, age: float, error
) -> None:
    heartbeat(tmp_path, pid=pid, age=age, error=error)
    assert not installer.healthy(
        output="state = running\npid = 5011", desired=desired(tmp_path), home=tmp_path
    )
