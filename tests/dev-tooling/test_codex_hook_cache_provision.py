"""Provisioner result selection for supervised Codex hook-cache observers."""

from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_codex_hook_cache_fixtures import DEV_TOOLING, observer, reconciler, write_payload


def test_a_newer_observer_error_governs_the_provisioner_result(tmp_path: Path) -> None:
    """A newer observer failure is not hidden by this run's successful reconcile."""
    module_path = DEV_TOOLING / "codex_hook_cache_provision.py"
    assert module_path.is_file()
    provision = importlib.import_module("codex_hook_cache_provision")
    home = tmp_path / "codex"
    home.mkdir()
    (home / "config.toml").write_text("[marketplaces.livespec-driver-codex]\n", encoding="utf-8")
    root = home / "plugins" / "cache" / "livespec-driver-codex" / "livespec"
    write_payload(root=root, version="0.6.1")
    state = reconciler.state_file(
        marketplace="livespec-driver-codex", plugin="livespec", codex_home_override=home
    )
    observer.write_status(
        path=observer.status_file(state_path=state),
        pid=os.getpid(),
        last_error="observer repair failed",
        reconcile_completed_at=(datetime.now(timezone.utc) + timedelta(minutes=1))
        .isoformat()
        .replace("+00:00", "Z"),
    )

    reports = provision.reconcile_all_for_provisioning(home=home)

    assert len(reports) == 1
    assert not reports[0].ok
    assert reports[0].marketplace == "livespec-driver-codex"
    assert reports[0].plugin == "livespec"
    assert reports[0].problems == (
        "livespec-driver-codex/livespec: observer reconcile failed: observer repair failed",
    )
