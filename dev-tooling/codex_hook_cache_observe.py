#!/usr/bin/env python3
"""Persistent observer for Codex-native Driver cache auto-upgrades.

`ensure-codex-plugins` only reconciles the hook cache when a human or a
gate runs it. Codex also upgrades marketplaces on its own at startup,
which replaces the versioned payload with no provisioning run to hang the
repair off. This observer watches the cache directory, waits until a
newly-appearing payload is complete, and then runs the same reconciler.

Like the reconciler it is repo-level `dev-tooling/` surface — never
shipped in the plugin bundle, never run from inside the Codex-managed
cache — and stdlib-only so bare `python3` provisioning can start it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import codex_hook_cache_reconcile as reconciler
from _codex_hook_cache_process import (
    STALE_AFTER_SECONDS,
    ensure,
    health,
    log_file,
    status_file,
    write_status,
)

POLL_SECONDS = 0.2
HEARTBEAT_SECONDS = 5.0
SETTLE_TIMEOUT_SECONDS = 120.0

# Re-exported so callers see one module API even though the liveness/process
# half lives in the sibling module.
__all__ = [
    "HEARTBEAT_SECONDS",
    "POLL_SECONDS",
    "SETTLE_TIMEOUT_SECONDS",
    "STALE_AFTER_SECONDS",
    "await_complete_payload",
    "ensure",
    "fingerprint",
    "health",
    "log_file",
    "main",
    "run_loop",
    "status_file",
    "write_status",
]


def fingerprint(*, root: Path) -> tuple[tuple[str, float], ...]:
    """Cheap signature of the cache's real payload set."""
    marks: list[tuple[str, float]] = []
    for name in reconciler.real_versions(root=root):
        try:
            marks.append((name, (root / name).stat().st_mtime))
        except OSError:
            continue
    return tuple(marks)


def await_complete_payload(
    *,
    root: Path,
    timeout: float = SETTLE_TIMEOUT_SECONDS,
    poll: float = POLL_SECONDS,
) -> tuple[str, ...]:
    """Block until the newest payload validates; returns the problems if it never does.

    Codex writes a new version directory incrementally, so a reconcile
    fired on first sight would alias `latest` at a half-written payload.
    Waiting for two consecutive identical, validating snapshots is what
    makes "complete" mean complete rather than "present".
    """
    deadline = time.monotonic() + timeout
    previous: tuple[tuple[str, float], ...] | None = None
    problems: tuple[str, ...] = ("payload never became complete",)
    while time.monotonic() < deadline:
        current = fingerprint(root=root)
        versions = reconciler.real_versions(root=root)
        if versions and current == previous:
            problems = reconciler.validate_payload(payload=root / versions[-1])
            if not problems:
                return ()
        previous = current
        time.sleep(poll)
    return problems


def run_loop(
    *,
    root: Path,
    state_path: Path,
    iterations: int | None = None,
    poll: float = POLL_SECONDS,
    settle_timeout: float = SETTLE_TIMEOUT_SECONDS,
) -> int:
    """Watch the cache and reconcile each completed payload change.

    The first iteration always reconciles: an observer that started after
    an upgrade it missed must repair the topology rather than adopt the
    broken state as its baseline.
    """
    status_path = status_file(state_path=state_path)
    seen: tuple[tuple[str, float], ...] | None = None
    last_error: str | None = None
    write_status(path=status_path, pid=os.getpid(), last_error=None)
    last_beat = time.monotonic()
    count = 0
    while iterations is None or count < iterations:
        count += 1
        current = fingerprint(root=root)
        if current != seen:
            seen = current
            problems = await_complete_payload(root=root, timeout=settle_timeout, poll=poll)
            if problems:
                last_error = "; ".join(problems)
            else:
                report = reconciler.reconcile(root=root, state_path=state_path)
                reconciler.report_to_stream(report=report, root=root)
                last_error = None if report.ok else "; ".join(report.problems)
            write_status(path=status_path, pid=os.getpid(), last_error=last_error)
            last_beat = time.monotonic()
        elif time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
            write_status(path=status_path, pid=os.getpid(), last_error=last_error)
            last_beat = time.monotonic()
        time.sleep(poll)
    return 1 if last_error else 0


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the standalone entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("run", "ensure", "status"))
    parser.add_argument("--codex-home", default=None)
    parser.add_argument("--marketplace", default=reconciler.DEFAULT_MARKETPLACE)
    parser.add_argument("--plugin", default=reconciler.DEFAULT_PLUGIN)
    parser.add_argument("--state", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run, start, or report on the observer."""
    args = build_parser().parse_args(argv)
    root = reconciler.cache_root(
        home=reconciler.codex_home(override=args.codex_home),
        marketplace=args.marketplace,
        plugin=args.plugin,
    )
    state_path = reconciler.state_file(override=args.state)
    if args.mode == "run":
        return run_loop(root=root, state_path=state_path)
    if args.mode == "ensure":
        ok, why = ensure(
            entry_point=Path(__file__).resolve(),
            interpreter=sys.executable,
            root=root,
            state_path=state_path,
        )
    else:
        ok, why = health(path=status_file(state_path=state_path))
    reconciler.emit(
        event=why if ok else f"codex hook cache observer is NOT healthy — {why}",
        level="info" if ok else "error",
        cache_root=str(root),
        mode=args.mode,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
