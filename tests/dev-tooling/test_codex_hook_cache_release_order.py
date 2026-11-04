"""Path continuity never waits on the release tag, and the release is fetched only when needed."""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import Iterator
from pathlib import Path

import codex_hook_cache_all
import pytest
from _codex_hook_release_source import ReleasePayload
from test_codex_hook_cache_fixtures import link_target, observer, reconciler, write_payload

MARKET = "market"
PLUGIN = "plugin"
UNOBTAINABLE = "release tag cannot be obtained for installed version"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A Codex home with one registered marketplace and an empty trust table."""
    codex = tmp_path / "codex"
    codex.mkdir()
    (codex / "config.toml").write_text(f"[marketplaces.{MARKET}]\n\n[hooks.state]\n", "utf-8")
    return codex


@pytest.fixture
def root(home: Path) -> Path:
    """The covered plugin's versioned cache directory."""
    return home / "plugins" / "cache" / MARKET / PLUGIN


def _fetches(*, monkeypatch: pytest.MonkeyPatch, home: Path, obtainable: bool) -> list[str]:
    """Replace the release source and record every version it is asked for."""
    fetched: list[str] = []

    @contextlib.contextmanager
    def source(
        *, config_path: Path, marketplace: str, plugin: str, version: str
    ) -> Iterator[ReleasePayload]:
        del config_path
        fetched.append(version)
        if obtainable:
            payload = home / "plugins" / "cache" / marketplace / plugin / version
            yield ReleasePayload(payload=payload, problem=None)
        else:
            yield ReleasePayload(payload=None, problem=f"{UNOBTAINABLE} {version}")

    monkeypatch.setattr(codex_hook_cache_all, "release_payload", source)
    return fetched


def _reconcile(*, home: Path) -> reconciler.Report:
    (report,) = reconciler.reconcile_all(home=home)
    return report


def test_an_unobtainable_release_does_not_stop_alias_repair(
    home: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow, unreachable or untagged remote leaves path continuity intact."""
    write_payload(root=root, version="1.0.0")
    _fetches(monkeypatch=monkeypatch, home=home, obtainable=True)
    assert _reconcile(home=home).ok
    shutil.rmtree(root / "1.0.0")
    write_payload(root=root, version="1.1.0")
    fetched = _fetches(monkeypatch=monkeypatch, home=home, obtainable=False)

    report = _reconcile(home=home)

    assert fetched == ["1.1.0"]
    assert not report.ok
    assert "plugin: unverified hook hooks/hooks.json:PreToolUse" in " ".join(report.problems)
    assert link_target(path=root / "latest") == "1.1.0"
    assert link_target(path=root / "1.0.0") == "latest"


def test_a_payload_that_fails_validation_never_reaches_the_release(
    home: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation precedes any network access."""
    payload = write_payload(root=root, version="1.0.0")
    (payload / "hooks" / "stop.py").unlink()
    fetched = _fetches(monkeypatch=monkeypatch, home=home, obtainable=True)

    report = _reconcile(home=home)

    assert not report.ok
    assert fetched == []


def test_the_release_is_not_fetched_while_codex_trust_matches_the_installed_bytes(
    home: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An offline host with intact trust is healthy and costs no clone per sweep."""
    write_payload(root=root, version="1.0.0")
    _fetches(monkeypatch=monkeypatch, home=home, obtainable=True)
    assert _reconcile(home=home).ok
    fetched = _fetches(monkeypatch=monkeypatch, home=home, obtainable=False)

    report = _reconcile(home=home)

    assert fetched == []
    assert report.ok


def test_rewritten_cache_bytes_make_trust_stale_and_the_release_is_fetched(
    home: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A same-version rewrite invalidates the content hash, so verification runs again."""
    write_payload(root=root, version="1.0.0")
    _fetches(monkeypatch=monkeypatch, home=home, obtainable=True)
    assert _reconcile(home=home).ok
    (root / "1.0.0" / ".codex-plugin" / "cache-metadata").write_text("rewritten", "utf-8")
    fetched = _fetches(monkeypatch=monkeypatch, home=home, obtainable=False)

    report = _reconcile(home=home)

    assert fetched == ["1.0.0"]
    assert not report.ok


def test_an_unrecognized_trust_format_is_reported_without_a_fetch_or_write(
    home: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The format failure names the plugin and still leaves the aliases repaired."""
    write_payload(root=root, version="1.0.0")
    config = home / "config.toml"
    config.write_text(f"[marketplaces.{MARKET}]\n\n[hooks.state]\nstray = 1\n", "utf-8")
    before = config.read_text("utf-8")
    fetched = _fetches(monkeypatch=monkeypatch, home=home, obtainable=True)

    report = _reconcile(home=home)

    assert fetched == []
    assert not report.ok
    assert "plugin: unrecognized Codex trust record format" in " ".join(report.problems)
    assert config.read_text("utf-8") == before
    assert link_target(path=root / "latest") == "1.0.0"


def _observe_failures(
    *, home: Path, monkeypatch: pytest.MonkeyPatch, retry_seconds: float, iterations: int
) -> int:
    calls: list[tuple[str, str] | None] = []

    def failing(
        *, home: Path, only: tuple[str, str] | None = None
    ) -> tuple[reconciler.Report, ...]:
        del home
        calls.append(only)
        report = reconciler.Report(
            ok=False,
            current_version="1.0.0",
            actions=(),
            problems=("unverified",),
            marketplace=MARKET,
            plugin=PLUGIN,
            completed_at_epoch=1.0,
        )
        return (report,)

    monkeypatch.setattr(reconciler, "reconcile_all", failing)
    observer.run_all_loop(home=home, poll=0.0, iterations=iterations, retry_seconds=retry_seconds)
    return len(calls)


def test_the_observer_retries_a_failed_reconcile_instead_of_settling_on_it(
    home: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unobtainable release is retried, so a transient outage is not permanent."""
    write_payload(root=root, version="1.0.0")

    calls = _observe_failures(home=home, monkeypatch=monkeypatch, retry_seconds=0.0, iterations=8)

    assert calls > 1


def test_the_observer_does_not_retry_a_failure_faster_than_its_retry_interval(
    home: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A persistent failure costs one release attempt per interval, not one per poll."""
    write_payload(root=root, version="1.0.0")

    calls = _observe_failures(
        home=home, monkeypatch=monkeypatch, retry_seconds=3600.0, iterations=8
    )

    assert calls == 1
