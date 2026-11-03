"""Release-verified trust continuity for Codex plugin hooks."""

from __future__ import annotations

import importlib
from pathlib import Path

from test_codex_hook_cache_fixtures import write_payload


def test_reconciler_trusts_only_hooks_verified_against_the_release(tmp_path: Path) -> None:
    """A matching release may restore every hook's Codex trust record."""
    module_path = Path(__file__).resolve().parents[2] / "dev-tooling" / "codex_hook_trust.py"

    assert module_path.is_file()
    trust = importlib.import_module("codex_hook_trust")
    cache = tmp_path / "codex" / "plugins" / "cache" / "market" / "plugin"
    payload = write_payload(root=cache, version="1.2.3")
    release = tmp_path / "release"
    release.mkdir()
    release_payload = write_payload(root=release, version="1.2.3")
    config = tmp_path / "codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[hooks.state]\n", encoding="utf-8")

    report = trust.reconcile_trust(
        config_path=config,
        marketplace="market",
        plugin="plugin",
        payload=payload,
        release_payload=release_payload,
    )

    assert report.ok
    assert len(report.trusted_hooks) == 2
    assert "trusted_content_hash" in config.read_text(encoding="utf-8")
