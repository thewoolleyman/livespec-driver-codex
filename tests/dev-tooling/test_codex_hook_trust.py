"""Release-verified trust continuity for Codex plugin hooks."""

from __future__ import annotations

import importlib
import subprocess
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


def test_codex_stop_hash_omits_an_empty_matcher_and_driver_content_hash_is_stable(
    tmp_path: Path,
) -> None:
    """Pin observed Codex hashes for an empty-matcher Stop hook and Driver 0.10.0."""
    release = importlib.import_module("codex_hook_release")
    trust = importlib.import_module("codex_hook_trust")
    handler = {
        "type": "command",
        "command": 'if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; '
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_wait_stop.py"',
        "timeout": 30,
    }
    stop_group = {"matcher": "", "hooks": [handler]}

    assert release._declaration_hash(event="Stop", group=stop_group, handler=handler) == (
        "sha256:dd9cca0d4acfc13247d1f9c7fae4bd5172b70ad70552c0dbff97744c9874dd14"
    )

    archive = subprocess.run(
        ["git", "archive", "v0.10.0", "livespec"], capture_output=True, check=True
    )
    archive_path = tmp_path / "driver.tar"
    archive_path.write_bytes(archive.stdout)
    unpacked = tmp_path / "release"
    unpacked.mkdir()
    subprocess.run(["tar", "-xf", str(archive_path), "-C", str(unpacked)], check=True)

    content_hash, problem = trust._plugin_content_hash(root=unpacked / "livespec")

    assert problem is None
    assert content_hash == "sha256:8f1f4a1f11d47abe6b6827979a9aa53db5fa0038d5774d14ef8d84497ef44776"
