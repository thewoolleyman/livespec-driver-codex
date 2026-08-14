"""Host-aware acceptance for the hook cache against the REAL Codex install.

Gated on `LIVESPEC_REQUIRE_CODEX_CACHE_TRANSITION=1` and on the `codex`
CLI being present, mirroring the live TUI picker acceptance: it skips
cleanly rather than failing where neither holds.

DELIBERATE NARROWING, stated honestly: this does NOT publish a new
Driver release to make the marketplace advance. It uses the REAL
installed payload — the host's actual manifest, hook registration, and
hook scripts — and drives a real version transition over a copy of it at
a scratch `CODEX_HOME`, which reproduces every step of a Codex
auto-upgrade except the release that triggers it. Publishing a release
from a test would couple the suite to the release pipeline, so that last
step stays out; everything downstream of it is exercised here.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from test_codex_hook_cache_fixtures import link_target, observer, reconciler

REQUIRE_ENV = "LIVESPEC_REQUIRE_CODEX_CACHE_TRANSITION"

pytestmark = [
    pytest.mark.skipif(
        os.environ.get(REQUIRE_ENV) != "1",
        reason=f"set {REQUIRE_ENV}=1 on a host with the Driver installed to enforce this leg",
    ),
    pytest.mark.skipif(
        shutil.which("codex") is None,
        reason="codex CLI not found; the real hook cache cannot be asserted against",
    ),
]


@pytest.fixture
def real_cache() -> Path:
    """The host's real versioned Driver plugin-cache directory."""
    root = reconciler.cache_root(home=reconciler.codex_home())
    if not root.is_dir():
        pytest.skip(f"{root} is absent; the Codex Driver is not installed on this host")
    return root


def test_the_real_cache_reconciles_to_a_validated_current_payload(
    real_cache: Path, tmp_path: Path
) -> None:
    """The reconciler is safe and effective against the host's real cache.

    The durable state record is redirected into `tmp_path` so the test
    never mutates the host's version history; the cache itself IS the
    subject, and reconciling it is idempotent by contract.
    """
    report = reconciler.reconcile(root=real_cache, state_path=tmp_path / "hook-cache-state.json")

    assert report.ok, report.problems
    assert report.current_version in reconciler.real_versions(root=real_cache)
    assert link_target(path=real_cache / "latest") == report.current_version
    assert not reconciler.validate_payload(payload=real_cache / "latest")


def test_every_retained_hook_path_resolves_through_latest(real_cache: Path, tmp_path: Path) -> None:
    """A hook path captured under a retired version still reaches the current payload."""
    assert reconciler.reconcile(root=real_cache, state_path=tmp_path / "hook-cache-state.json").ok
    current = reconciler.real_versions(root=real_cache)[-1]
    aliases = [
        entry
        for entry in real_cache.iterdir()
        if entry.is_symlink() and entry.name != reconciler.LATEST_ALIAS
    ]
    scripts, problems = reconciler.declared_hook_scripts(payload=real_cache / current)
    assert not problems

    for alias in aliases:
        assert link_target(path=alias) == reconciler.LATEST_ALIAS
        for script in scripts:
            retained = alias / script.relative_to(real_cache / current)
            assert retained.is_file(), f"{retained} does not resolve to a hook script"
            assert retained.resolve() == script.resolve()


def test_a_real_payload_transition_keeps_captured_hook_paths_resolving(
    real_cache: Path, tmp_path: Path
) -> None:
    """The ratified scenario, driven over the real installed payload.

    A scratch `CODEX_HOME` receives a copy of the host's actual current
    payload; the observer then watches while that payload is replaced the
    way Codex replaces one — the new version written incrementally, the
    old version directory removed. The hook path an older session
    captured must still resolve to a validated script afterwards, and
    `latest` must not have moved while the new payload was half-written.
    """
    current = reconciler.real_versions(root=real_cache)[-1]
    cache = tmp_path / "codex" / "plugins" / "cache" / "livespec-driver-codex" / "livespec"
    shutil.copytree(real_cache / current, cache / current, symlinks=True)
    state = tmp_path / "state" / "hook-cache-state.json"
    assert observer.run_loop(root=cache, state_path=state, iterations=1, poll=0.01) == 0
    captured = [
        cache / current / script.relative_to(real_cache / current)
        for script in reconciler.declared_hook_scripts(payload=real_cache / current)[0]
    ]
    assert all(path.is_file() for path in captured)

    successor = _bump(version=current)
    shutil.copytree(cache / current / ".codex-plugin", cache / successor / ".codex-plugin")
    assert (
        observer.run_loop(root=cache, state_path=state, iterations=1, poll=0.01, settle_timeout=0.3)
        == 1
    )
    assert link_target(path=cache / "latest") == current

    shutil.copytree(cache / current / "hooks", cache / successor / "hooks")
    shutil.rmtree(cache / current)
    assert observer.run_loop(root=cache, state_path=state, iterations=1, poll=0.01) == 0

    assert link_target(path=cache / "latest") == successor
    assert link_target(path=cache / current) == reconciler.LATEST_ALIAS
    for path in captured:
        assert path.is_file(), f"{path} stopped resolving across the transition"
    assert not reconciler.validate_payload(payload=cache / current)


def _bump(*, version: str) -> str:
    major, minor = version.split(".")[:2]
    return f"{major}.{int(minor) + 1}.0"
