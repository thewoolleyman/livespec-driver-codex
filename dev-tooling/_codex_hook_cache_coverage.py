"""Covered-plugin discovery for the Codex hook-cache reconciler."""

from __future__ import annotations

import json
import re
from pathlib import Path

from _codex_hook_cache_payload import declares_hooks, real_versions

_MARKETPLACE_TABLE = re.compile(r'^\s*\[marketplaces\.("(?:[^"\\\\]|\\\\.)*"|[^]\s]+)]\s*(?:#.*)?$')
_TABLE = re.compile(r"^\s*\[")
_FIELD = re.compile(r'^\s*(source_type|source)\s*=\s*("(?:[^"\\\\]|\\\\.)*")\s*(?:#.*)?$')
_VERSION_NAME = re.compile(r"^\d+(\.\d+){2}([-.][0-9A-Za-z.-]+)?$")


def covered_plugin_roots(*, home: Path) -> tuple[tuple[str, str, Path], ...]:
    """Return cache roots for hook-declaring plugins in configured marketplaces."""
    marketplaces = configured_marketplaces(home=home)
    cache = home / "plugins" / "cache"
    found: list[tuple[str, str, Path]] = []
    for marketplace in marketplaces:
        marketplace_root = cache / marketplace
        if not marketplace_root.is_dir():
            continue
        for root in marketplace_root.iterdir():
            versions = real_versions(root=root)
            if versions and declares_hooks(payload=root / versions[-1]):
                found.append((marketplace, root.name, root))
    return tuple(found)


def configured_marketplaces(*, home: Path) -> tuple[str, ...]:
    """Read configured marketplace names except Codex-curated local sources.

    The provisioner is bare Python 3.10, so this intentionally reads the
    small table shape Codex writes instead of adding a TOML dependency.
    """
    return tuple(
        name
        for name, fields in _marketplace_records(home=home)
        if not _is_codex_curated(fields=fields, home=home)
    )


def codex_curated_cache_aliases(*, home: Path) -> tuple[tuple[str, str, Path, Path], ...]:
    """Return Driver-shaped direct aliases in Codex-curated plugin caches."""
    cache = home / "plugins" / "cache"
    found: list[tuple[str, str, Path, Path]] = []
    for marketplace, fields in _marketplace_records(home=home):
        if not _is_codex_curated(fields=fields, home=home):
            continue
        marketplace_root = cache / marketplace
        if not marketplace_root.is_dir():
            continue
        for root in marketplace_root.iterdir():
            if not root.is_dir():
                continue
            for child in root.iterdir():
                if _is_driver_alias(path=child):
                    found.append((marketplace, root.name, root, child))
    return tuple(found)


def _marketplace_records(*, home: Path) -> tuple[tuple[str, dict[str, str]], ...]:
    """Read marketplace names and the two source fields used for classification."""
    try:
        lines = (home / "config.toml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    records: list[tuple[str, dict[str, str]]] = []
    active: tuple[str, dict[str, str]] | None = None
    for line in lines:
        table = _MARKETPLACE_TABLE.match(line)
        if table:
            try:
                raw = table.group(1)
                name = json.loads(raw) if raw.startswith('"') else raw
            except json.JSONDecodeError:
                active = None
                continue
            fields: dict[str, str] = {}
            active = (name, fields)
            records.append(active)
            continue
        if _TABLE.match(line):
            active = None
            continue
        field = _FIELD.match(line)
        if active is None or field is None:
            continue
        try:
            active[1][field.group(1)] = json.loads(field.group(2))
        except json.JSONDecodeError:
            active = None
    return tuple(records)


def _is_codex_curated(*, fields: dict[str, str], home: Path) -> bool:
    """Whether a local source resolves inside a Codex-managed source directory."""
    if fields.get("source_type") != "local":
        return False
    source = fields.get("source")
    if source is None:
        return False
    candidate = Path(source).expanduser()
    if not candidate.is_absolute():
        return False
    try:
        resolved_source = candidate.resolve(strict=True)
    except OSError:
        return False
    for root in (home / ".tmp" / "bundled-marketplaces", Path.home() / ".cache" / "codex-runtimes"):
        try:
            resolved_root = root.resolve(strict=True)
        except OSError:
            continue
        if resolved_source.is_relative_to(resolved_root):
            return True
    return False


def _is_driver_alias(*, path: Path) -> bool:
    """Whether `path` has the relative direct-child alias shape we create."""
    if not path.is_symlink():
        return False
    target = path.readlink()
    if target.is_absolute():
        return False
    return path.name == "latest" or (
        _VERSION_NAME.match(path.name) is not None and target == Path("latest")
    )
