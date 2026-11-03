"""Deterministic mock-cache tests for the persistent hook-cache observer.

The observer's loop is driven with a bounded `iterations` count so the
tests exercise the real polling body without ever running forever, and
the liveness record is asserted directly rather than through a spawned
process.
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import time
from pathlib import Path

import pytest
from test_codex_hook_cache_fixtures import link_target, observer, write_payload

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    """An empty versioned plugin-cache directory."""
    root = tmp_path / "plugins" / "cache" / "livespec-driver-codex" / "livespec"
    root.mkdir(parents=True)
    return root


@pytest.fixture
def state(tmp_path: Path) -> Path:
    """A state-record path outside the cache."""
    return tmp_path / "state" / "hook-cache-state.json"


def test_a_completed_payload_change_triggers_reconciliation(cache: Path, state: Path) -> None:
    """A new version appearing mid-loop is aliased once it validates."""
    write_payload(root=cache, version="0.6.0")
    assert observer.run_loop(root=cache, state_path=state, iterations=1, poll=0.01) == 0
    assert link_target(path=cache / "latest") == "0.6.0"

    write_payload(root=cache, version="0.6.1")

    assert observer.run_loop(root=cache, state_path=state, iterations=1, poll=0.01) == 0
    assert link_target(path=cache / "latest") == "0.6.1"


def test_an_incomplete_payload_is_not_aliased(cache: Path, state: Path) -> None:
    """The observer waits for completeness instead of aliasing a half-written payload."""
    write_payload(root=cache, version="0.6.0")
    assert observer.run_loop(root=cache, state_path=state, iterations=1, poll=0.01) == 0
    write_payload(root=cache, version="0.6.1", drop_hook_script=True)

    exit_code = observer.run_loop(
        root=cache, state_path=state, iterations=1, poll=0.01, settle_timeout=0.3
    )

    assert exit_code == 1
    assert link_target(path=cache / "latest") == "0.6.0"


def test_a_manifest_declared_default_hooks_file_must_exist_before_retargeting(
    cache: Path, state: Path
) -> None:
    """A manifest-only successor is incomplete, not a hookless payload."""
    write_payload(root=cache, version="0.6.0")
    assert observer.reconciler.reconcile(root=cache, state_path=state).ok

    successor = cache / "0.6.1"
    (successor / ".codex-plugin").mkdir(parents=True)
    manifest = {
        "name": "livespec",
        "version": "0.6.1",
        "hooks": "./hooks/hooks.json",
    }
    (successor / ".codex-plugin" / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = observer.reconciler.reconcile(root=cache, state_path=state)

    missing_hooks = successor / "hooks" / "hooks.json"
    assert not report.ok
    assert any(str(missing_hooks) in problem for problem in report.problems)
    assert link_target(path=cache / "latest") == "0.6.0"
    assert (
        observer.run_loop(root=cache, state_path=state, iterations=1, poll=0.01, settle_timeout=0.3)
        == 1
    )
    assert link_target(path=cache / "latest") == "0.6.0"


def test_await_complete_payload_reports_the_validation_problems(cache: Path) -> None:
    """A payload that never completes surfaces why, rather than timing out silently."""
    write_payload(root=cache, version="0.6.1", drop_hook_script=True)

    problems = observer.await_complete_payload(root=cache, timeout=0.5, poll=0.01)

    assert problems
    assert any("is missing" in problem for problem in problems)


def test_health_requires_a_status_record(tmp_path: Path) -> None:
    """No record at all means no healthy observer."""
    healthy, why = observer.health(path=tmp_path / "observer.json")

    assert not healthy
    assert "no observer status record" in why


def test_health_rejects_a_stale_heartbeat(tmp_path: Path) -> None:
    """A live process with a frozen heartbeat is unhealthy, not healthy."""
    record = tmp_path / "observer.json"
    observer.write_status(path=record, pid=os.getpid(), last_error=None)

    healthy, why = observer.health(path=record, now=time.time() + observer.STALE_AFTER_SECONDS + 1)

    assert not healthy
    assert "stale" in why


def test_health_rejects_a_dead_pid(tmp_path: Path) -> None:
    """A record whose process is gone is unhealthy."""
    record = tmp_path / "observer.json"
    observer.write_status(path=record, pid=2**22 - 1, last_error=None)

    healthy, why = observer.health(path=record)

    assert not healthy
    assert "not running" in why


def test_health_rejects_a_recorded_reconcile_failure(tmp_path: Path) -> None:
    """An observer that is running but failing to repair is not healthy."""
    record = tmp_path / "observer.json"
    observer.write_status(path=record, pid=os.getpid(), last_error="payload never completed")

    healthy, why = observer.health(path=record)

    assert not healthy
    assert "last reconcile failed" in why


def test_health_accepts_a_fresh_successful_record(tmp_path: Path) -> None:
    """A live pid with a fresh heartbeat and no error is the healthy case."""
    record = tmp_path / "observer.json"
    observer.write_status(path=record, pid=os.getpid(), last_error=None)

    healthy, why = observer.health(path=record)

    assert healthy
    assert "healthy" in why


def test_health_rejects_a_startup_heartbeat_before_first_reconcile(tmp_path: Path) -> None:
    """A live observer is not healthy for a plugin until it repaired that plugin once."""
    record = tmp_path / "observer.json"
    observer.write_status(path=record, pid=os.getpid(), last_error=None)
    startup_record = json.loads(record.read_text(encoding="utf-8"))
    startup_record["completed_reconcile"] = False
    record.write_text(json.dumps(startup_record), encoding="utf-8")

    healthy, why = observer.health(path=record)

    assert not healthy
    assert "first reconcile" in why


def test_runtime_paths_stay_outside_the_codex_managed_cache(state: Path, cache: Path) -> None:
    """The liveness record and log live beside the state file, never in the cache."""
    assert not observer.status_file(state_path=state).is_relative_to(cache)
    assert not observer.log_file(state_path=state).is_relative_to(cache)


def test_status_mode_reports_an_absent_observer_as_a_failure(tmp_path: Path, state: Path) -> None:
    """`status` is the health verification the provisioner calls; absence is non-zero."""
    exit_code = observer.main(
        ["status", "--codex-home", str(tmp_path), "--state", str(state)],
    )

    assert exit_code == 1


def test_observer_service_definition_and_provisioning_check_are_shipped() -> None:
    """Linux hosts get a user unit and provisioning rejects an unsupervised observer."""
    unit = REPO_ROOT / "dev-tooling" / "livespec-codex-hook-cache-observer.service"
    provisioner = (REPO_ROOT / "dev-tooling" / "ensure-codex-plugins.sh").read_text(
        encoding="utf-8"
    )

    assert unit.is_file()
    assert "[Service]" in unit.read_text(encoding="utf-8")
    assert "systemctl --user is-active" in provisioner
    assert "not running under the installed supervisor unit" in provisioner


def test_macos_launchagent_is_a_generalized_supervisor_with_portable_python() -> None:
    """The shipped LaunchAgent runs one all-plugin observer on either Mac architecture."""
    agent = REPO_ROOT / "dev-tooling" / "com.livespec.codex-hook-cache-observer.plist"

    assert agent.is_file()
    definition = plistlib.loads(agent.read_bytes())

    assert definition["Label"] == "com.livespec.codex-hook-cache-observer"
    assert definition["ProgramArguments"][-2:] == ["run", "--all"]
    assert "-c" in definition["ProgramArguments"]
    assert "--marketplace" not in definition["ProgramArguments"]
    assert "--plugin" not in definition["ProgramArguments"]
    assert definition["RunAtLoad"] is True
    assert definition["KeepAlive"] is True
    assert definition["ThrottleInterval"] > 0
    assert "/opt/homebrew/bin" in definition["EnvironmentVariables"]["PATH"]
    assert "/usr/local/bin" in definition["EnvironmentVariables"]["PATH"]


def test_macos_supervisor_check_reports_an_errored_launchagent_without_takeover(
    tmp_path: Path,
) -> None:
    """Provisioning reports the managed observer's error; it never replaces it."""
    commands = tmp_path / "commands"
    commands.mkdir()
    calls = tmp_path / "calls"
    scripts = {
        "codex": "#!/bin/sh\nexit 0\n",
        "uname": "#!/bin/sh\necho Darwin\n",
        "launchctl": (
            '#!/bin/sh\nprintf \'%s\\n\' "launchctl $*" >> "$CALLS"\n'
            "printf 'state = running\\npid = 4242\\n'\n"
        ),
        "python3": (
            '#!/bin/sh\nprintf \'%s\\n\' "python3 $*" >> "$CALLS"\n'
            'case "$*" in *codex_hook_cache_observe.py*) '
            "echo 'market/alpha: last reconcile failed' >&2; exit 1;; esac\n"
        ),
    }
    for name, body in scripts.items():
        command = commands / name
        command.write_text(body, encoding="utf-8")
        command.chmod(0o755)
    env = {**os.environ, "CALLS": str(calls), "PATH": f"{commands}:{os.environ['PATH']}"}

    result = subprocess.run(
        ["/usr/bin/bash", str(REPO_ROOT / "dev-tooling" / "ensure-codex-plugins.sh")],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "market/alpha: last reconcile failed" in result.stderr
    recorded = calls.read_text(encoding="utf-8")
    assert "launchctl print gui/" in recorded
    assert "codex_hook_cache_observe.py status --all --expected-pid 4242" in recorded
    assert "ensure" not in recorded
    assert "bootstrap" not in recorded
    assert "bootout" not in recorded


def test_linux_provisioner_uses_its_newer_reconcile_instead_of_an_old_observer_error(
    tmp_path: Path,
) -> None:
    """An explicit repair supersedes an earlier observer failure for that plugin."""
    commands = tmp_path / "commands"
    commands.mkdir()
    calls = tmp_path / "calls"
    scripts = {
        "codex": "#!/bin/sh\nexit 0\n",
        "uname": "#!/bin/sh\necho Linux\n",
        "systemctl": "#!/bin/sh\nexit 0\n",
        "python3": (
            '#!/bin/sh\nprintf \'%s\\n\' "python3 $*" >> "$CALLS"\n'
            'case "$*" in *codex_hook_cache_observe.py\ provision\ --all*) exit 0;; esac\n'
            'case "$*" in *codex_hook_cache_reconcile.py*) exit 0;; esac\n'
            "echo 'market/alpha: earlier observer reconcile failed' >&2; exit 1\n"
        ),
    }
    for name, body in scripts.items():
        command = commands / name
        command.write_text(body, encoding="utf-8")
        command.chmod(0o755)

    result = subprocess.run(
        ["/usr/bin/bash", str(REPO_ROOT / "dev-tooling" / "ensure-codex-plugins.sh")],
        capture_output=True,
        check=False,
        env={**os.environ, "CALLS": str(calls), "PATH": f"{commands}:{os.environ['PATH']}"},
        text=True,
    )

    assert result.returncode == 0
    recorded = calls.read_text(encoding="utf-8")
    assert "codex_hook_cache_observe.py provision --all" in recorded
    assert "codex_hook_cache_observe.py ensure" not in recorded


def test_macos_supervisor_check_rejects_a_loaded_but_exited_launchagent(tmp_path: Path) -> None:
    """A stale launchd job record is not evidence that its observer is running."""
    commands = tmp_path / "commands"
    commands.mkdir()
    scripts = {
        "codex": "#!/bin/sh\nexit 0\n",
        "uname": "#!/bin/sh\necho Darwin\n",
        "launchctl": "#!/bin/sh\nprintf 'state = exited\\npid = 4242\\n'\n",
        "python3": "#!/bin/sh\nexit 0\n",
    }
    for name, body in scripts.items():
        command = commands / name
        command.write_text(body, encoding="utf-8")
        command.chmod(0o755)

    result = subprocess.run(
        ["/usr/bin/bash", str(REPO_ROOT / "dev-tooling" / "ensure-codex-plugins.sh")],
        capture_output=True,
        check=False,
        env={**os.environ, "PATH": f"{commands}:{os.environ['PATH']}"},
        text=True,
    )

    assert result.returncode == 1
    assert "not running under the installed LaunchAgent" in result.stderr


def test_all_plugin_observer_uses_a_non_busy_poll_interval() -> None:
    """The systemd all-plugin loop leaves meaningful time between cache scans."""
    assert observer.POLL_SECONDS >= 1.0


def test_shell_hook_entrypoints_are_validated_without_python_compilation(tmp_path: Path) -> None:
    """A shell hook is executable payload, not Python source to compile."""
    payload = write_payload(root=tmp_path, version="0.6.1")
    hooks = payload / "hooks" / "hooks.json"
    registration = json.loads(hooks.read_text(encoding="utf-8"))
    registration["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = (
        'bash "${CLAUDE_PLUGIN_ROOT}/hooks/guard.sh"'
    )
    hooks.write_text(json.dumps(registration), encoding="utf-8")
    (payload / "hooks" / "guard.py").unlink()
    (payload / "hooks" / "guard.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    assert not observer.reconciler.validate_payload(payload=payload)


def test_observer_status_is_per_plugin_and_honors_codex_home(tmp_path: Path) -> None:
    """One plugin's heartbeat never supplies status for another plugin."""
    home = tmp_path / "codex"
    alpha = observer.reconciler.state_file(
        marketplace="market", plugin="alpha", codex_home_override=home
    )
    beta = observer.reconciler.state_file(
        marketplace="market", plugin="beta", codex_home_override=home
    )
    alpha_status = observer.status_file(state_path=alpha)
    beta_status = observer.status_file(state_path=beta)
    observer.write_status(path=alpha_status, pid=os.getpid(), last_error="broken alpha")
    observer.write_status(path=beta_status, pid=os.getpid(), last_error=None)

    assert alpha_status != beta_status
    assert (
        observer.main(
            ["status", "--codex-home", str(home), "--marketplace", "market", "--plugin", "alpha"]
        )
        == 1
    )
    assert (
        observer.main(
            ["status", "--codex-home", str(home), "--marketplace", "market", "--plugin", "beta"]
        )
        == 0
    )
