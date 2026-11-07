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
from _codex_hook_cache_coverage import codex_curated_cache_aliases, covered_plugin_roots
from _codex_hook_cache_fingerprint import all_fingerprint as _all_fingerprint
from _codex_hook_cache_fingerprint import fingerprint
from _codex_hook_cache_process import (
    STALE_AFTER_SECONDS,
    ensure,
    health,
    health_after_provisioner,
    log_file,
    status_file,
    write_status,
)
from _codex_hook_cache_report import provision_all, status_all
from _codex_hook_release_source import RELEASE_FETCH_BUDGET_SECONDS

POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 5.0
SETTLE_TIMEOUT_SECONDS = 120.0
RETRY_AFTER_FAILURE_SECONDS = 300.0


def trust_reconcile_latency_seconds(*, covered_plugins: int) -> float:
    """Worst-case time from lost trust to trust restored or the plugin reported.

    Detection takes two polls (the change is seen, then confirmed stable). The
    reconcile then spends at most one release-fetch budget per covered plugin that
    is reconciled ahead of, or as, the affected one in the same sweep.
    """
    return 2 * POLL_SECONDS + covered_plugins * RELEASE_FETCH_BUDGET_SECONDS


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
    "health_after_provisioner",
    "log_file",
    "main",
    "provision_all",
    "run_all_loop",
    "run_loop",
    "status_all",
    "status_file",
    "trust_reconcile_latency_seconds",
    "write_status",
]


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
    reconcile_completed_at_epoch: float | None = None
    write_status(path=status_path, pid=os.getpid(), last_error=None, completed_reconcile=False)
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
            reconcile_completed_at_epoch = time.time()
            write_status(
                path=status_path,
                pid=os.getpid(),
                last_error=last_error,
                completed_reconcile=True,
                reconcile_completed_at_epoch=reconcile_completed_at_epoch,
            )
            last_beat = time.monotonic()
        elif time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
            write_status(
                path=status_path,
                pid=os.getpid(),
                last_error=last_error,
                completed_reconcile=reconcile_completed_at_epoch is not None,
                reconcile_completed_at_epoch=reconcile_completed_at_epoch,
            )
            last_beat = time.monotonic()
        time.sleep(poll)
    return 1 if last_error else 0


def run_all_loop(
    *,
    home: Path,
    poll: float = POLL_SECONDS,
    iterations: int | None = None,
    retry_seconds: float = RETRY_AFTER_FAILURE_SECONDS,
) -> None:
    """Watch payload and trust state; see `trust_reconcile_latency_seconds` for the bound.

    A reconcile that reported a problem is retried every `retry_seconds` even with no
    further change, so a transient release outage is not a permanent failure; the first
    attempt, and its report, still happen within the stated latency.
    """
    seen: dict[tuple[str, str], tuple[object, ...]] = {}
    settled: dict[tuple[str, str], tuple[object, ...]] = {}
    last_beat: dict[tuple[str, str], float] = {}
    errors: dict[tuple[str, str], str | None] = {}
    completed_at: dict[tuple[str, str], float] = {}
    retry_at: dict[tuple[str, str], float] = {}
    count = 0
    while iterations is None or count < iterations:
        count += 1
        _record_curated_alias_notices(home=home)
        roots = covered_plugin_roots(home=home)
        for marketplace, plugin, root in roots:
            key = (marketplace, plugin)
            state_path = reconciler.state_file(
                marketplace=marketplace, plugin=plugin, codex_home_override=home
            )
            current = _all_fingerprint(root=root, config_path=home / "config.toml")
            if seen.get(key) != current:
                seen[key] = current
                continue
            retry_due = bool(errors.get(key)) and time.monotonic() >= retry_at.get(key, 0.0)
            if settled.get(key) != current or retry_due:
                reports = reconciler.reconcile_all(home=home, only=key)
                report = next(
                    (
                        candidate
                        for candidate in reports
                        if candidate.marketplace == marketplace and candidate.plugin == plugin
                    ),
                    None,
                )
                errors[key] = (
                    "reconcile did not report the covered plugin"
                    if report is None
                    else "; ".join(report.problems)
                )
                refreshed = _all_fingerprint(root=root, config_path=home / "config.toml")
                seen[key] = refreshed
                settled[key] = refreshed
                completed_at[key] = time.time()
                retry_at[key] = time.monotonic() + retry_seconds
                write_status(
                    path=status_file(state_path=state_path),
                    pid=os.getpid(),
                    last_error=errors[key] or None,
                    reconcile_completed_at_epoch=completed_at[key],
                )
                last_beat[key] = time.monotonic()
            elif time.monotonic() - last_beat.get(key, 0.0) >= HEARTBEAT_SECONDS:
                write_status(
                    path=status_file(state_path=state_path),
                    pid=os.getpid(),
                    last_error=errors.get(key),
                    completed_reconcile=key in completed_at,
                    reconcile_completed_at_epoch=completed_at.get(key),
                )
                last_beat[key] = time.monotonic()
        time.sleep(poll)


def _record_curated_alias_notices(*, home: Path) -> None:
    """Persist notices for aliases we deliberately leave in Codex-owned caches."""
    notices: dict[tuple[str, str], list[str]] = {}
    for marketplace, plugin, _, alias in codex_curated_cache_aliases(home=home):
        notices.setdefault((marketplace, plugin), []).append(str(alias))
    for (marketplace, plugin), paths in notices.items():
        write_status(
            path=status_file(
                state_path=reconciler.state_file(
                    marketplace=marketplace, plugin=plugin, codex_home_override=home
                )
            ),
            pid=os.getpid(),
            last_error=None,
            notices=tuple(paths),
        )


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the standalone entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("run", "ensure", "status", "provision"))
    parser.add_argument("--codex-home", default=None)
    parser.add_argument("--marketplace", default=reconciler.DEFAULT_MARKETPLACE)
    parser.add_argument("--plugin", default=reconciler.DEFAULT_PLUGIN)
    parser.add_argument("--state", default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--expected-pid", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run, start, or report on the observer."""
    args = build_parser().parse_args(argv)
    home = reconciler.codex_home(override=args.codex_home)
    if args.mode == "run" and args.all:
        run_all_loop(home=home)
        return 0
    if args.mode == "status" and args.all:
        return status_all(home=home, expected_pid=args.expected_pid)
    if args.mode == "provision" and args.all:
        return provision_all(home=home, expected_pid=args.expected_pid)
    root = reconciler.cache_root(
        home=home,
        marketplace=args.marketplace,
        plugin=args.plugin,
    )
    state_path = reconciler.state_file(
        override=args.state,
        marketplace=args.marketplace,
        plugin=args.plugin,
        codex_home_override=home,
    )
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
        ok, why = health(path=status_file(state_path=state_path), expected_pid=args.expected_pid)
    reconciler.emit(
        event=why if ok else f"codex hook cache observer is NOT healthy — {why}",
        level="info" if ok else "error",
        cache_root=str(root),
        mode=args.mode,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
