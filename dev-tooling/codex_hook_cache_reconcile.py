#!/usr/bin/env python3
"""Cache-independent reconciler for the Codex Driver hook cache.

Codex's background marketplace auto-upgrade deletes and replaces the
versioned plugin-cache directory a running session already captured its
Stop/PreToolUse hook commands against, so those absolute hook paths stop
resolving mid-session. This reconciler keeps a one-hop alias topology
`old-version -> latest -> current-version` inside the cache so every
retained hook path keeps resolving to a validated payload.

It is repo-level `dev-tooling/` surface, never shipped inside the plugin
bundle and never copied into the Codex-managed cache, and it is
stdlib-only so it runs under the bare `python3` that provisioning uses
before any virtualenv exists.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from _codex_hook_cache_payload import (
    VERSION_RE,
    declared_hook_scripts,
    read_json,
    real_versions,
    validate_payload,
    version_sort_key,
)

# Re-exported so callers (the observer, the test suite) see one module API
# even though the discovery/validation half lives in the sibling module.
__all__ = [
    "DEFAULT_MARKETPLACE",
    "DEFAULT_PLUGIN",
    "LATEST_ALIAS",
    "STATE_ENV",
    "Report",
    "cache_root",
    "codex_home",
    "declared_hook_scripts",
    "emit",
    "main",
    "real_versions",
    "reconcile",
    "report_to_stream",
    "state_file",
    "validate_payload",
]

DEFAULT_MARKETPLACE = "livespec-driver-codex"
DEFAULT_PLUGIN = "livespec"
LATEST_ALIAS = "latest"
STATE_ENV = "LIVESPEC_CODEX_HOOK_CACHE_STATE"


@dataclasses.dataclass(frozen=True)
class Report:
    """Outcome of one reconcile pass."""

    ok: bool
    current_version: str | None
    actions: tuple[str, ...]
    problems: tuple[str, ...]


def codex_home(*, override: str | None = None) -> Path:
    """Resolve CODEX_HOME, honouring the env override Codex itself reads."""
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def cache_root(
    *,
    home: Path,
    marketplace: str = DEFAULT_MARKETPLACE,
    plugin: str = DEFAULT_PLUGIN,
) -> Path:
    """The versioned plugin-cache directory holding `<version>/` payloads."""
    return home / "plugins" / "cache" / marketplace / plugin


def state_file(*, override: str | None = None) -> Path:
    """Durable record of every version this reconciler has observed.

    Deliberately outside the Codex-managed cache: the cache is exactly the
    tree Codex deletes and replaces, so state kept there cannot survive the
    event it exists to repair.
    """
    if override:
        return Path(override).expanduser()
    env_override = os.environ.get(STATE_ENV)
    if env_override:
        return Path(env_override).expanduser()
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base).expanduser() / "livespec-driver-codex" / "hook-cache-state.json"


def _alias_status(*, path: Path) -> str:
    """Classify an alias slot as `absent`, `managed`, or `unsafe`.

    `managed` is narrow by design — a symlink whose target is a single
    relative name inside the cache directory. Anything else (a real file
    or directory, an absolute target, a traversing target) is never
    overwritten.
    """
    if path.is_symlink():
        target = Path.readlink(path).as_posix()
        if target in {"", ".", ".."} or "/" in target:
            return "unsafe"
        return "managed"
    if path.exists():
        return "unsafe"
    return "absent"


def _link(*, path: Path, target: str) -> bool:
    """Point `path` at `target`, atomically. True when something changed."""
    if path.is_symlink() and Path.readlink(path).as_posix() == target:
        return False
    staging = path.with_name(f".{path.name}.livespec-reconcile.{os.getpid()}")
    staging.unlink(missing_ok=True)
    staging.symlink_to(target)
    staging.replace(path)
    return True


def _load_state(*, path: Path) -> tuple[str, ...]:
    parsed, _ = read_json(path=path)
    if parsed is None:
        return ()
    observed = parsed.get("observed_versions")
    if not isinstance(observed, list):
        return ()
    return tuple(name for name in observed if isinstance(name, str) and VERSION_RE.match(name))


def _save_state(*, path: Path, observed: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"observed_versions": list(observed)}, indent=2, sort_keys=True) + "\n"
    staging = path.with_name(f".{path.name}.livespec-reconcile.{os.getpid()}")
    staging.write_text(body, encoding="utf-8")
    staging.replace(path)


def reconcile(*, root: Path, state_path: Path) -> Report:
    """Bring the cache's alias topology in line with the current payload."""
    versions = real_versions(root=root)
    if not versions:
        return Report(
            ok=False,
            current_version=None,
            actions=(),
            problems=(f"{root}: no version payload directory found",),
        )
    current = versions[-1]
    problems = validate_payload(payload=root / current)
    if problems:
        return Report(ok=False, current_version=current, actions=(), problems=problems)

    observed = tuple(
        sorted(set(_load_state(path=state_path)) | set(versions), key=version_sort_key)
    )
    desired = {LATEST_ALIAS: current}
    for name in observed:
        if name != current and name not in versions:
            desired[name] = LATEST_ALIAS

    unsafe = [
        f"{root / name}: refusing to replace an unmanaged or malformed path"
        for name in desired
        if _alias_status(path=root / name) == "unsafe"
    ]
    if unsafe:
        return Report(ok=False, current_version=current, actions=(), problems=tuple(unsafe))

    _save_state(path=state_path, observed=observed)
    actions = tuple(
        f"{name} -> {target}"
        for name, target in desired.items()
        if _link(path=root / name, target=target)
    )
    return Report(ok=True, current_version=current, actions=actions, problems=())


def emit(*, event: str, level: str, **fields: object) -> None:
    """Write one structured JSON line, mirroring the other dev-tooling gates."""
    payload = {
        **fields,
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    stream = sys.stderr if level == "error" else sys.stdout
    stream.write(json.dumps(payload) + "\n")
    stream.flush()


def report_to_stream(*, report: Report, root: Path) -> None:
    """Render a reconcile outcome loudly enough to be read in CI logs."""
    if report.ok:
        emit(
            event="codex hook cache reconciled",
            level="info",
            cache_root=str(root),
            current_version=report.current_version,
            actions=list(report.actions),
        )
        return
    for problem in report.problems:
        emit(
            event="codex hook cache reconciliation FAILED — hook continuity is NOT assured",
            level="error",
            cache_root=str(root),
            current_version=report.current_version,
            problem=problem,
        )


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the standalone entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--codex-home", default=None)
    parser.add_argument("--marketplace", default=DEFAULT_MARKETPLACE)
    parser.add_argument("--plugin", default=DEFAULT_PLUGIN)
    parser.add_argument("--state", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Reconcile once and report; non-zero means hook continuity is not assured."""
    args = build_parser().parse_args(argv)
    root = cache_root(
        home=codex_home(override=args.codex_home),
        marketplace=args.marketplace,
        plugin=args.plugin,
    )
    report = reconcile(root=root, state_path=state_file(override=args.state))
    report_to_stream(report=report, root=root)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
