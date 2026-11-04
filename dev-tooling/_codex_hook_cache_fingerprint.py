"""Cheap change signatures of a covered plugin's cache and its trust-record file."""

from __future__ import annotations

import os
from pathlib import Path

import codex_hook_cache_reconcile as reconciler

__all__ = ["all_fingerprint", "fingerprint"]


def fingerprint(*, root: Path) -> tuple[tuple[str, float], ...]:
    """Cheap signature of the cache's real payload set."""
    marks: list[tuple[str, float]] = []
    for name in reconciler.real_versions(root=root):
        try:
            marks.append((name, (root / name).stat().st_mtime))
        except OSError:
            continue
    return tuple(marks)


def all_fingerprint(*, root: Path, config_path: Path) -> tuple[object, ...]:
    """Include file-level payload marks and the trust-record file.

    A directory's own mtime does not move when an existing file inside it is
    rewritten, so each file's mtime and size are fingerprinted as well.
    """
    payload = fingerprint(root=root)
    files = tuple(
        mark for name in reconciler.real_versions(root=root) for mark in _tree_marks(root / name)
    )
    try:
        return (*payload, files, ("config.toml", config_path.stat().st_mtime_ns))
    except OSError:
        return (*payload, files, ("config.toml", -1))


def _tree_marks(top: Path) -> list[tuple[str, int, int]]:
    marks: list[tuple[str, int, int]] = []
    for directory, _, names in os.walk(top, followlinks=False):
        for name in sorted(names):
            path = Path(directory) / name
            try:
                stat = path.lstat()
            except OSError:
                continue
            marks.append((str(path.relative_to(top.parent)), stat.st_mtime_ns, stat.st_size))
    return marks
