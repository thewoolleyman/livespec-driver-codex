"""Deterministic mock-cache tests for the persistent hook-cache observer.

The observer's loop is driven with a bounded `iterations` count so the
tests exercise the real polling body without ever running forever, and
the liveness record is asserted directly rather than through a spawned
process.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from test_codex_hook_cache_fixtures import link_target, observer, write_payload


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
