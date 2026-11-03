"""A slow or absent release remote is reported, never raised."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest
from test_codex_hook_cache_fixtures import DEV_TOOLING  # noqa: F401  — puts dev-tooling on sys.path


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
