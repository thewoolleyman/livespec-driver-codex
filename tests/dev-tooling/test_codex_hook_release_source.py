"""A slow or absent release remote is reported, never raised."""

from __future__ import annotations

import importlib
import subprocess
import types
from pathlib import Path

import pytest
from test_codex_hook_cache_fixtures import observer


def test_a_git_clone_timeout_is_reported_as_an_unobtainable_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A timed-out clone yields a problem so sibling plugins still reconcile."""
    source = importlib.import_module("_codex_hook_release_source")

    def hang(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="git clone", timeout=90)

    monkeypatch.setattr(source.subprocess, "run", hang)
    config = tmp_path / "config.toml"
    config.write_text(
        '[marketplaces.market]\nsource_type = "git"\nsource = "https://example.invalid/x.git"\n',
        encoding="utf-8",
    )

    with source.release_payload(
        config_path=config, marketplace="market", plugin="plugin", version="1.2.3"
    ) as released:
        assert released.payload is None
        assert released.problem is not None
        assert "release tag cannot be obtained" in released.problem
        assert "timed out" in released.problem


def test_a_missing_git_executable_is_reported_as_an_unobtainable_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unlaunchable git is the same loud, per-plugin failure."""
    source = importlib.import_module("_codex_hook_release_source")

    def absent(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("git")

    monkeypatch.setattr(source.subprocess, "run", absent)

    problem = source.checkout_release(
        source="https://example.invalid/x.git", version="1.2.3", checkout=tmp_path / "source"
    )

    assert problem is not None
    assert "release tag cannot be obtained" in problem


def test_both_tag_spellings_share_one_fetch_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hung remote costs one plugin the fetch budget once, not once per tag spelling."""
    source = importlib.import_module("_codex_hook_release_source")
    clock = [0.0]
    timeouts: list[float] = []

    def hang(*_args: object, timeout: float, **_kwargs: object) -> object:
        timeouts.append(timeout)
        clock[0] += timeout
        raise subprocess.TimeoutExpired(cmd="git clone", timeout=timeout)

    monkeypatch.setattr(source.subprocess, "run", hang)
    monkeypatch.setattr(
        source, "time", types.SimpleNamespace(monotonic=lambda: clock[0]), raising=False
    )

    problem = source.checkout_release(
        source="https://example.invalid/x.git", version="1.2.3", checkout=tmp_path / "source"
    )

    assert sum(timeouts) <= source.RELEASE_FETCH_BUDGET_SECONDS
    assert problem is not None
    assert "release tag cannot be obtained" in problem
    assert "fetch budget" in problem


def test_the_stated_trust_latency_covers_detection_and_every_plugin_fetch() -> None:
    """The observer's stated bound is two polls plus one fetch budget per covered plugin."""
    source = importlib.import_module("_codex_hook_release_source")

    for plugins in (1, 3):
        assert observer.trust_reconcile_latency_seconds(covered_plugins=plugins) == (
            2 * observer.POLL_SECONDS + plugins * source.RELEASE_FETCH_BUDGET_SECONDS
        )
