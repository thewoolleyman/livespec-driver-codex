"""All-covered-plugin orchestration for Codex hook cache reconciliation."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from _codex_hook_cache_coverage import covered_plugin_roots
from _codex_hook_release_source import release_payload
from codex_hook_cache_reconcile import Report, real_versions, reconcile, state_file
from codex_hook_release import untrusted_hook_problems


def reconcile_all(*, home: Path) -> tuple[Report, ...]:
    """Reconcile every covered plugin and restore only release-verified trust."""
    reports: list[Report] = []
    for marketplace, plugin, root in covered_plugin_roots(home=home):
        versions = real_versions(root=root)
        current = versions[-1] if versions else None
        if current is None:
            report = reconcile(
                root=root,
                state_path=state_file(
                    marketplace=marketplace, plugin=plugin, codex_home_override=home
                ),
                marketplace=marketplace,
                plugin=plugin,
            )
        else:
            report = _reconcile_version(
                home=home,
                marketplace=marketplace,
                plugin=plugin,
                root=root,
                current=current,
            )
        reports.append(
            dataclasses.replace(
                report,
                marketplace=marketplace,
                plugin=plugin,
                problems=tuple(f"{marketplace}/{plugin}: {problem}" for problem in report.problems),
            )
        )
    return tuple(reports)


def _reconcile_version(
    *, home: Path, marketplace: str, plugin: str, root: Path, current: str
) -> Report:
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
            state_path=state_file(marketplace=marketplace, plugin=plugin, codex_home_override=home),
            config_path=home / "config.toml",
            marketplace=marketplace,
            plugin=plugin,
            release_payload=released.payload,
        )
