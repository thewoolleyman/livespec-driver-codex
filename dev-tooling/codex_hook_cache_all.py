"""Release-verified trust reconciliation for every covered Codex plugin."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path

from _codex_hook_cache_coverage import covered_plugin_roots
from _codex_hook_release_source import release_payload
from codex_hook_cache_reconcile import Report, real_versions, reconcile, state_file
from codex_hook_release import untrusted_hook_problems


def reconcile_all(*, home: Path) -> tuple[Report, ...]:
    """Reconcile each covered plugin without trusting cache bytes as a release."""
    reports: list[Report] = []
    for marketplace, plugin, root in covered_plugin_roots(home=home):
        report = _reconcile_plugin(
            home=home,
            marketplace=marketplace,
            plugin=plugin,
            root=root,
        )
        reports.append(
            dataclasses.replace(
                report,
                marketplace=marketplace,
                plugin=plugin,
                completed_at_epoch=time.time(),
                problems=tuple(f"{marketplace}/{plugin}: {problem}" for problem in report.problems),
            )
        )
    return tuple(reports)


def _reconcile_plugin(*, home: Path, marketplace: str, plugin: str, root: Path) -> Report:
    versions = real_versions(root=root)
    current = versions[-1] if versions else None
    if current is None:
        return reconcile(
            root=root,
            state_path=state_file(
                marketplace=marketplace,
                plugin=plugin,
                codex_home_override=home,
            ),
            marketplace=marketplace,
            plugin=plugin,
        )
    with release_payload(
        config_path=home / "config.toml",
        marketplace=marketplace,
        plugin=plugin,
        version=current,
    ) as released:
        if released.payload is None:
            return Report(
                ok=False,
                current_version=current,
                actions=(),
                problems=untrusted_hook_problems(
                    plugin=plugin,
                    payload=root / current,
                    reason=released.problem or "release tag cannot be verified",
                ),
            )
        return reconcile(
            root=root,
            state_path=state_file(
                marketplace=marketplace,
                plugin=plugin,
                codex_home_override=home,
            ),
            config_path=home / "config.toml",
            marketplace=marketplace,
            plugin=plugin,
            release_payload=released.payload,
        )
