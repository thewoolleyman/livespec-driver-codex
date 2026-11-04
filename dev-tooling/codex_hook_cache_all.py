"""Release-verified trust reconciliation for every covered Codex plugin."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path

from _codex_hook_cache_coverage import covered_plugin_roots
from _codex_hook_release_source import release_payload
from codex_hook_cache_reconcile import Report, reconcile, state_file
from codex_hook_release import untrusted_hook_problems
from codex_hook_trust import reconcile_trust, trust_status


def reconcile_all(*, home: Path, only: tuple[str, str] | None = None) -> tuple[Report, ...]:
    """Reconcile each covered plugin (or just `only`) without trusting cache bytes."""
    reports: list[Report] = []
    for marketplace, plugin, root in covered_plugin_roots(home=home):
        if only is not None and only != (marketplace, plugin):
            continue
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
    config_path = home / "config.toml"
    paths = reconcile(
        root=root,
        state_path=state_file(marketplace=marketplace, plugin=plugin, codex_home_override=home),
        marketplace=marketplace,
        plugin=plugin,
    )
    current = paths.current_version
    if not paths.ok or current is None:
        return paths
    payload = root / current
    status = trust_status(
        config_path=config_path, marketplace=marketplace, plugin=plugin, payload=payload
    )
    if status.problems:
        return dataclasses.replace(paths, ok=False, problems=status.problems)
    if status.trusted:
        return paths
    with release_payload(
        config_path=config_path, marketplace=marketplace, plugin=plugin, version=current
    ) as released:
        if released.payload is None:
            problems = untrusted_hook_problems(
                plugin=plugin,
                payload=payload,
                reason=released.problem or "release tag cannot be verified",
            )
        else:
            trust = reconcile_trust(
                config_path=config_path,
                marketplace=marketplace,
                plugin=plugin,
                payload=payload,
                release_payload=released.payload,
            )
            problems = trust.problems
    return paths if not problems else dataclasses.replace(paths, ok=False, problems=problems)
