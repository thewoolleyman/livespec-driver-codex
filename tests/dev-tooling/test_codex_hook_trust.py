"""Release-verified trust continuity for Codex plugin hooks."""

from __future__ import annotations

import importlib
import re
import subprocess
from pathlib import Path

import pytest
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


def test_reconciler_replaces_a_stale_record_without_duplicate_toml_tables(
    tmp_path: Path,
) -> None:
    """Same-version re-materialization must repair a record Codex made stale."""
    trust = importlib.import_module("codex_hook_trust")
    cache = tmp_path / "codex" / "plugins" / "cache" / "market" / "plugin"
    payload = write_payload(root=cache, version="1.2.3")
    release = tmp_path / "release"
    release.mkdir()
    release_payload = write_payload(root=release, version="1.2.3")
    config = tmp_path / "codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[hooks.state]\n", encoding="utf-8")
    assert trust.reconcile_trust(
        config_path=config,
        marketplace="market",
        plugin="plugin",
        payload=payload,
        release_payload=release_payload,
    ).ok
    stale = re.sub(
        r'trusted_content_hash = ".*"',
        'trusted_content_hash = "sha256:stale"',
        config.read_text(encoding="utf-8"),
        count=1,
    )
    config.write_text(stale, encoding="utf-8")

    report = trust.reconcile_trust(
        config_path=config,
        marketplace="market",
        plugin="plugin",
        payload=payload,
        release_payload=release_payload,
    )

    repaired = config.read_text(encoding="utf-8")
    assert report.ok
    assert repaired.count("[hooks.state.") == 2
    assert "sha256:stale" not in repaired


def test_reconciler_names_every_untrusted_hook_when_one_entrypoint_changes(
    tmp_path: Path,
) -> None:
    """A changed script leaves every hook untrusted, so every hook is reported."""
    trust = importlib.import_module("codex_hook_trust")
    cache = tmp_path / "codex" / "plugins" / "cache" / "market" / "plugin"
    payload = write_payload(root=cache, version="1.2.3")
    release = tmp_path / "release"
    release.mkdir()
    release_payload = write_payload(root=release, version="1.2.3")
    (payload / "hooks" / "guard.py").write_text("changed\n", encoding="utf-8")
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

    assert not report.ok
    assert len(report.problems) == 2
    problems = " ".join(report.problems)
    assert "hooks/hooks.json:PreToolUse" in problems
    assert "hooks/hooks.json:Stop" in problems


def test_reconciler_rejects_fields_under_a_non_keyed_state_table_without_writing(
    tmp_path: Path,
) -> None:
    """An unknown trust shape below a bare hooks.state table fails closed."""
    trust = importlib.import_module("codex_hook_trust")
    cache = tmp_path / "codex" / "plugins" / "cache" / "market" / "plugin"
    payload = write_payload(root=cache, version="1.2.3")
    release = tmp_path / "release"
    release.mkdir()
    release_payload = write_payload(root=release, version="1.2.3")
    config = tmp_path / "codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    original = "[hooks.state]\nfuture_trust_schema = { v = 2 }\n"
    config.write_text(original, encoding="utf-8")

    report = trust.reconcile_trust(
        config_path=config,
        marketplace="market",
        plugin="plugin",
        payload=payload,
        release_payload=release_payload,
    )

    assert not report.ok
    assert report.trusted_hooks == ()
    assert "plugin" in " ".join(report.problems)
    assert config.read_text(encoding="utf-8") == original


def test_reconciler_keeps_unrelated_tables_after_a_replaced_trust_table(
    tmp_path: Path,
) -> None:
    """Repairing a stale trust record must not delete neighbouring Codex config."""
    trust = importlib.import_module("codex_hook_trust")
    cache = tmp_path / "codex" / "plugins" / "cache" / "market" / "plugin"
    payload = write_payload(root=cache, version="1.2.3")
    release = tmp_path / "release"
    release.mkdir()
    release_payload = write_payload(root=release, version="1.2.3")
    config = tmp_path / "codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[hooks.state]\n", encoding="utf-8")
    assert trust.reconcile_trust(
        config_path=config,
        marketplace="market",
        plugin="plugin",
        payload=payload,
        release_payload=release_payload,
    ).ok
    stale = re.sub(
        r'trusted_content_hash = ".*"',
        'trusted_content_hash = "sha256:stale"',
        config.read_text(encoding="utf-8"),
    )
    config.write_text(stale + '\n[projects."/work"]\ntrust_level = "trusted"\n', encoding="utf-8")

    report = trust.reconcile_trust(
        config_path=config,
        marketplace="market",
        plugin="plugin",
        payload=payload,
        release_payload=release_payload,
    )

    repaired = config.read_text(encoding="utf-8")
    assert report.ok
    assert "sha256:stale" not in repaired
    assert '[projects."/work"]\ntrust_level = "trusted"\n' in repaired


@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired(cmd="git", timeout=90), FileNotFoundError("git")],
)
def test_release_checkout_reports_a_slow_or_missing_git_as_unverifiable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """A clone that cannot run must yield an error string, not abort the caller."""
    source = importlib.import_module("_codex_hook_release_source")

    def fail_clone(*_args: object, **_kwargs: object) -> object:
        raise failure

    monkeypatch.setattr(source.subprocess, "run", fail_clone)

    problem = source.checkout_release(
        source="https://example.invalid/market.git",
        version="1.2.3",
        checkout=tmp_path / "source",
    )

    assert isinstance(problem, str)
    assert "release tag cannot be obtained" in problem
