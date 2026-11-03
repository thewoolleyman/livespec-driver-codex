#!/usr/bin/env python3
"""Reconcile hook caches and select the newest observer/provisioner result.

This is the one-shot half of hook-cache provisioning. It deliberately does
not manage the observer process: a platform supervisor owns that lifecycle,
while this command reconciles aliases and reports the newest per-plugin result
available from the observer status record.
"""

from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime, timezone
from pathlib import Path

import codex_hook_cache_reconcile as reconciler
from _codex_hook_cache_coverage import covered_plugin_roots
from _codex_hook_cache_process import read_status, status_file

__all__ = ["main", "reconcile_all_for_provisioning"]


@dataclasses.dataclass(frozen=True)
class ObserverResult:
    """The observer result recorded for one plugin, if it is trustworthy."""

    completed_at: datetime | None
    last_error: str | None
    problem: str | None


def _parse_completed_at(*, status: dict[str, object]) -> datetime | None:
    """Read a comparable UTC completion time, rejecting malformed values."""
    value = status.get("reconcile_completed_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _observer_result(*, state_path: Path, now: datetime) -> ObserverResult:
    """Read the observer record, keeping unusable times conservatively newer."""
    status = read_status(path=status_file(state_path=state_path))
    if status is None:
        return ObserverResult(None, None, "observer has no status record")
    completed_at = _parse_completed_at(status=status)
    last_error = status.get("last_error")
    error = last_error if isinstance(last_error, str) and last_error else None
    if completed_at is None:
        return ObserverResult(None, error, "observer has no usable reconcile completion time")
    if completed_at > now:
        return ObserverResult(None, error, "observer reconcile completion time is in the future")
    return ObserverResult(completed_at, error, None)


def _report_from_observer(
    *,
    observer_result: ObserverResult,
    provisioner_report: reconciler.Report,
    provisioner_completed_at: datetime,
) -> reconciler.Report:
    """Apply the contract's observer-wins-on-equal-time result selection."""
    observer_is_newer = (
        observer_result.completed_at is None
        or observer_result.completed_at >= provisioner_completed_at
    )
    if observer_is_newer and observer_result.last_error is not None:
        return dataclasses.replace(
            provisioner_report,
            ok=False,
            problems=(f"observer reconcile failed: {observer_result.last_error}",),
        )
    if observer_is_newer and observer_result.problem is not None:
        return dataclasses.replace(
            provisioner_report,
            ok=False,
            problems=(observer_result.problem,),
        )
    if observer_is_newer:
        return dataclasses.replace(provisioner_report, ok=True, problems=())
    return provisioner_report


def reconcile_all_for_provisioning(*, home: Path) -> tuple[reconciler.Report, ...]:
    """Reconcile every covered cache and return its newest recorded result."""
    reports: list[reconciler.Report] = []
    for marketplace, plugin, root in covered_plugin_roots(home=home):
        state_path = reconciler.state_file(
            marketplace=marketplace,
            plugin=plugin,
            codex_home_override=home,
        )
        provisioner_report = reconciler.reconcile(root=root, state_path=state_path)
        completed_at = datetime.now(timezone.utc)
        result = _report_from_observer(
            observer_result=_observer_result(state_path=state_path, now=completed_at),
            provisioner_report=provisioner_report,
            provisioner_completed_at=completed_at,
        )
        reports.append(
            dataclasses.replace(
                result,
                marketplace=marketplace,
                plugin=plugin,
                problems=tuple(f"{marketplace}/{plugin}: {problem}" for problem in result.problems),
            )
        )
    return tuple(reports)


def main(argv: list[str] | None = None) -> int:
    """Run the one-shot provisioner reconciliation and print final reports."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--codex-home", default=None)
    args = parser.parse_args(argv)
    home = reconciler.codex_home(override=args.codex_home)
    reports = reconcile_all_for_provisioning(home=home)
    for report in reports:
        reconciler.report_to_stream(
            report=report,
            root=reconciler.cache_root(
                home=home,
                marketplace=report.marketplace or reconciler.DEFAULT_MARKETPLACE,
                plugin=report.plugin or reconciler.DEFAULT_PLUGIN,
            ),
        )
    return 0 if all(report.ok for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
