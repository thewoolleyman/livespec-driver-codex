"""Safe cache-alias and durable-version-state primitives for reconciliation."""

from __future__ import annotations

import json
import os
from pathlib import Path

from _codex_hook_cache_payload import VERSION_RE, read_json


def alias_status(*, path: Path) -> str:
    """Classify an alias slot as ``absent``, ``managed``, or ``unsafe``."""
    if path.is_symlink():
        target = Path.readlink(path).as_posix()
        if target in {"", ".", ".."} or "/" in target:
            return "unsafe"
        return "managed"
    if path.exists():
        return "unsafe"
    return "absent"


def link(*, path: Path, target: str) -> bool:
    """Point ``path`` at ``target`` atomically; report whether it changed."""
    if path.is_symlink() and Path.readlink(path).as_posix() == target:
        return False
    staging = path.with_name(f".{path.name}.livespec-reconcile.{os.getpid()}")
    staging.unlink(missing_ok=True)
    staging.symlink_to(target)
    staging.replace(path)
    return True


def load_state(*, path: Path) -> tuple[str, ...]:
    """Read previously observed, version-shaped cache directories."""
    parsed, _ = read_json(path=path)
    if parsed is None:
        return ()
    observed = parsed.get("observed_versions")
    if not isinstance(observed, list):
        return ()
    return tuple(name for name in observed if isinstance(name, str) and VERSION_RE.match(name))


def save_state(*, path: Path, observed: tuple[str, ...]) -> None:
    """Persist observed versions atomically outside Codex's replaceable cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"observed_versions": list(observed)}, indent=2, sort_keys=True) + "\n"
    staging = path.with_name(f".{path.name}.livespec-reconcile.{os.getpid()}")
    staging.write_text(body, encoding="utf-8")
    staging.replace(path)
