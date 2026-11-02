"""Witnesses for the delegated pre-commit aggregate wiring."""

from __future__ import annotations

import re
from pathlib import Path

from livespec_dev_tooling.config import load_delegated_pre_commit

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repository_config_opts_in_to_delegated_pre_commit() -> None:
    """The released pre-commit delegate is explicitly enabled for this repository."""
    assert load_delegated_pre_commit(repo_root=_REPO_ROOT) is True


def test_dev_tooling_pin_includes_the_pre_commit_bootstrap_fix() -> None:
    """Every declared pin selects a release at or after the repaired v1.153.0."""
    config = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    tag_match = re.search(
        r'^livespec-dev-tooling = \{ git = "[^"]+", tag = "(v[^"]+)" \}$',
        config,
        flags=re.MULTILINE,
    )
    assert tag_match is not None
    tag = tag_match.group(1)

    assert tuple(int(part) for part in tag.removeprefix("v").split(".")) >= (1, 153, 0)

    lock = (_REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert lock.count(f"tag={tag}") == 2
