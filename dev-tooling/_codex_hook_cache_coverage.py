"""Covered-plugin discovery for the Codex hook-cache reconciler."""

from __future__ import annotations

import re
from pathlib import Path

from _codex_hook_cache_payload import declares_hooks, real_versions

_MARKETPLACE_TABLE = re.compile(r"^\s*\[marketplaces\.([^]\s]+)]\s*(?:#.*)?$")


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
    """Read marketplace table names from the host's Codex TOML file.

    This intentionally reads only the simple table form Codex writes and
    needs no TOML dependency under the bare Python 3.10 provisioner.
    """
    try:
        lines = (home / "config.toml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    return tuple(match.group(1) for line in lines if (match := _MARKETPLACE_TABLE.match(line)))
