"""Per-plugin health reporting for the shared Codex hook-cache observer."""

from __future__ import annotations

from pathlib import Path

import codex_hook_cache_reconcile as reconciler
from _codex_hook_cache_coverage import covered_plugin_roots
from _codex_hook_cache_process import health, health_after_provisioner, status_file

__all__ = [
    "provision_all",
    "status_all",
]


def status_all(*, home: Path, expected_pid: int | None = None) -> int:
    """Report health for every covered plugin under one shared observer."""
    results: list[bool] = []
    for marketplace, plugin, root in covered_plugin_roots(home=home):
        state_path = reconciler.state_file(
            marketplace=marketplace, plugin=plugin, codex_home_override=home
        )
        ok, why = health(path=status_file(state_path=state_path), expected_pid=expected_pid)
        reconciler.emit(
            event=why if ok else f"codex hook cache observer is NOT healthy — {why}",
            level="info" if ok else "error",
            cache_root=str(root),
            marketplace=marketplace,
            plugin=plugin,
            mode="status",
        )
        results.append(ok)
    return 0 if all(results) else 1


def provision_all(*, home: Path, expected_pid: int | None = None) -> int:
    """Reconcile covered plugins and report the newer observer or local result."""
    reports = {
        (report.marketplace, report.plugin): report
        for report in reconciler.reconcile_all(home=home)
    }
    results: list[bool] = []
    for marketplace, plugin, root in covered_plugin_roots(home=home):
        report = reports[(marketplace, plugin)]
        ok, why = health_after_provisioner(
            path=status_file(
                state_path=reconciler.state_file(
                    marketplace=marketplace, plugin=plugin, codex_home_override=home
                )
            ),
            provisioner_ok=report.ok,
            provisioner_problem="; ".join(report.problems),
            provisioner_completed_at_epoch=report.completed_at_epoch or 0.0,
            expected_pid=expected_pid,
        )
        reconciler.emit(
            event=why if ok else f"codex hook cache observer is NOT healthy — {why}",
            level="info" if ok else "error",
            cache_root=str(root),
            marketplace=marketplace,
            plugin=plugin,
            mode="provision",
        )
        results.append(ok)
    return 0 if all(results) else 1
