"""Deterministic mock-cache integration tests for the hook-cache reconciler.

Every case builds a throwaway Codex plugin cache under `tmp_path` and
drives the real reconciler against it, so discovery, validation, the
one-hop topology, idempotence, and the refusal paths are exercised
end-to-end without touching the host's cache.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_codex_hook_cache_fixtures import link_target, reconciler, write_payload


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    """An empty versioned plugin-cache directory."""
    root = tmp_path / "plugins" / "cache" / "livespec-driver-codex" / "livespec"
    root.mkdir(parents=True)
    return root


@pytest.fixture
def state(tmp_path: Path) -> Path:
    """A state-record path outside the cache, as the contract requires."""
    return tmp_path / "state" / "hook-cache-state.json"


def test_discovery_ignores_aliases_and_picks_the_newest_payload(cache: Path) -> None:
    """Version discovery reads real directories, never the aliases beside them."""
    write_payload(root=cache, version="0.6.0")
    write_payload(root=cache, version="0.10.0")
    write_payload(root=cache, version="0.9.0")
    (cache / "latest").symlink_to("0.9.0")

    assert reconciler.real_versions(root=cache) == ("0.6.0", "0.9.0", "0.10.0")


def test_reconcile_points_latest_at_the_current_payload(cache: Path, state: Path) -> None:
    """`latest` resolves to the newest validated payload."""
    write_payload(root=cache, version="0.6.1")

    report = reconciler.reconcile(root=cache, state_path=state)

    assert report.ok
    assert report.current_version == "0.6.1"
    assert link_target(path=cache / "latest") == "0.6.1"


def test_retained_old_version_resolves_through_latest_in_one_hop(cache: Path, state: Path) -> None:
    """A version the reconciler saw before, now deleted, aliases to `latest` — not past it."""
    write_payload(root=cache, version="0.6.0")
    assert reconciler.reconcile(root=cache, state_path=state).ok

    _delete_tree(path=cache / "0.6.0")
    write_payload(root=cache, version="0.6.1")
    report = reconciler.reconcile(root=cache, state_path=state)

    assert report.ok
    assert link_target(path=cache / "0.6.0") == "latest"
    assert link_target(path=cache / "latest") == "0.6.1"
    assert (cache / "0.6.0" / "hooks" / "stop.py").is_file()


def test_backfill_is_bounded_to_versions_the_reconciler_recorded(cache: Path, state: Path) -> None:
    """Only versions in the durable state record are backfilled."""
    write_payload(root=cache, version="0.6.1")
    assert reconciler.reconcile(root=cache, state_path=state).ok

    assert json.loads(state.read_text(encoding="utf-8"))["observed_versions"] == ["0.6.1"]
    assert not (cache / "0.5.0").exists()


def test_a_malformed_payload_is_rejected_without_retargeting_latest(
    cache: Path, state: Path
) -> None:
    """A newer payload whose hook does not compile never becomes `latest`."""
    write_payload(root=cache, version="0.6.0")
    assert reconciler.reconcile(root=cache, state_path=state).ok
    write_payload(root=cache, version="0.6.2", hook_body="def broken(:\n")

    report = reconciler.reconcile(root=cache, state_path=state)

    assert not report.ok
    assert any("does not compile" in problem for problem in report.problems)
    assert link_target(path=cache / "latest") == "0.6.0"


def test_an_incomplete_payload_is_rejected(cache: Path, state: Path) -> None:
    """A declared hook script that is missing counts as a mid-write payload."""
    write_payload(root=cache, version="0.6.1", drop_hook_script=True)

    report = reconciler.reconcile(root=cache, state_path=state)

    assert not report.ok
    assert any("is missing" in problem for problem in report.problems)
    assert not (cache / "latest").exists()


def test_a_manifest_without_a_hooks_entry_is_rejected(cache: Path, state: Path) -> None:
    """Validation starts at the manifest, not at a guessed hooks path."""
    write_payload(root=cache, version="0.6.1", manifest_hooks=None)

    report = reconciler.reconcile(root=cache, state_path=state)

    assert not report.ok
    assert any("declares no `hooks` entry" in problem for problem in report.problems)


def test_rerunning_an_already_reconciled_cache_changes_nothing(cache: Path, state: Path) -> None:
    """Idempotence: a second pass still verifies and reports success, but acts."""
    write_payload(root=cache, version="0.6.1")
    assert reconciler.reconcile(root=cache, state_path=state).ok

    report = reconciler.reconcile(root=cache, state_path=state)

    assert report.ok
    assert report.actions == ()


def test_complete_real_version_directories_are_preserved(cache: Path, state: Path) -> None:
    """An older payload that is still on disk is left exactly as it was."""
    older = write_payload(root=cache, version="0.6.0")
    write_payload(root=cache, version="0.6.1")
    before = sorted(path.name for path in (older / "hooks").iterdir())

    assert reconciler.reconcile(root=cache, state_path=state).ok

    assert not (older).is_symlink()
    assert sorted(path.name for path in (older / "hooks").iterdir()) == before


def test_an_unmanaged_file_in_an_alias_slot_is_refused_loudly(cache: Path, state: Path) -> None:
    """`latest` occupying a real file is never clobbered; the pass fails instead."""
    write_payload(root=cache, version="0.6.1")
    (cache / "latest").write_text("someone else's file", encoding="utf-8")

    report = reconciler.reconcile(root=cache, state_path=state)

    assert not report.ok
    assert any("refusing to replace" in problem for problem in report.problems)
    assert (cache / "latest").read_text(encoding="utf-8") == "someone else's file"


def test_a_symlink_escaping_the_cache_is_refused_loudly(
    cache: Path, state: Path, tmp_path: Path
) -> None:
    """An alias pointing outside the cache directory is malformed, not managed."""
    write_payload(root=cache, version="0.6.1")
    (cache / "latest").symlink_to(tmp_path / "elsewhere")

    report = reconciler.reconcile(root=cache, state_path=state)

    assert not report.ok
    assert any("refusing to replace" in problem for problem in report.problems)


def test_an_empty_cache_is_reported_as_a_failure(cache: Path, state: Path) -> None:
    """No payload means no hook continuity, and that is reported rather than assumed."""
    report = reconciler.reconcile(root=cache, state_path=state)

    assert not report.ok
    assert report.current_version is None


def test_main_exits_non_zero_when_reconciliation_fails(tmp_path: Path, state: Path) -> None:
    """The entry point's exit status is the provisioning-visible failure signal."""
    exit_code = reconciler.main(
        ["--codex-home", str(tmp_path), "--state", str(state)],
    )

    assert exit_code == 1


def test_main_exits_zero_on_a_healthy_cache(tmp_path: Path, cache: Path, state: Path) -> None:
    """A validated cache reconciles cleanly through the entry point."""
    write_payload(root=cache, version="0.6.1")

    assert reconciler.main(["--codex-home", str(tmp_path), "--state", str(state)]) == 0
    assert link_target(path=cache / "latest") == "0.6.1"


def test_state_file_defaults_outside_the_codex_managed_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The durable record must not live in the tree Codex deletes."""
    monkeypatch.delenv(reconciler.STATE_ENV, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))

    resolved = reconciler.state_file()

    assert not resolved.is_relative_to(tmp_path / "codex")


def _delete_tree(*, path: Path) -> None:
    for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        child.rmdir() if child.is_dir() else child.unlink()
    path.rmdir()
