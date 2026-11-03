"""Deterministic mock-cache integration tests for the hook-cache reconciler.

Every case builds a throwaway Codex plugin cache under `tmp_path` and
drives the real reconciler against it, so discovery, validation, the
one-hop topology, idempotence, and the refusal paths are exercised
end-to-end without touching the host's cache.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from test_codex_hook_cache_fixtures import link_target, observer, reconciler, write_payload


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


def test_reconcile_all_covers_registered_plugins_with_manifest_and_default_hooks(
    tmp_path: Path,
) -> None:
    """Every registered hook plugin gets its own retained-version alias chain."""
    home = tmp_path / "codex"
    _write_config(home=home, marketplaces=("first", "second"))
    first = home / "plugins" / "cache" / "first" / "default-only"
    second = home / "plugins" / "cache" / "second" / "manifest-only"
    _write_default_only_payload(root=first, version="1.0.0")
    _write_manifest_only_payload(root=second, version="1.0.0")
    assert all(report.ok for report in reconciler.reconcile_all(home=home))

    _delete_tree(path=first / "1.0.0")
    _delete_tree(path=second / "1.0.0")
    _write_default_only_payload(root=first, version="1.1.0")
    _write_manifest_only_payload(root=second, version="1.1.0")

    reports = reconciler.reconcile_all(home=home)

    assert all(report.ok for report in reports)
    assert link_target(path=first / "1.0.0") == "latest"
    assert link_target(path=first / "latest") == "1.1.0"
    assert link_target(path=second / "1.0.0") == "latest"
    assert link_target(path=second / "latest") == "1.1.0"


def test_reconcile_all_names_a_broken_plugin_and_continues_with_siblings(tmp_path: Path) -> None:
    """One malformed payload reports its identity without blocking its sibling."""
    home = tmp_path / "codex"
    _write_config(home=home, marketplaces=("first", "second"))
    broken = home / "plugins" / "cache" / "first" / "broken"
    healthy = home / "plugins" / "cache" / "second" / "healthy"
    broken_payload = write_payload(root=broken, version="1.0.0")
    (broken_payload / "hooks" / "stop.py").unlink()
    write_payload(root=healthy, version="1.0.0")

    reports = reconciler.reconcile_all(home=home)

    broken_report = next(report for report in reports if report.plugin == "broken")
    healthy_report = next(report for report in reports if report.plugin == "healthy")
    assert not broken_report.ok
    assert "first/broken" in " ".join(broken_report.problems)
    assert "command" in " ".join(broken_report.problems)
    assert healthy_report.ok
    assert link_target(path=healthy / "latest") == "1.0.0"


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


def test_a_malformed_manifest_hooks_entry_is_rejected(cache: Path, state: Path) -> None:
    """A malformed manifest declaration is not excused by the default registration."""
    payload = write_payload(root=cache, version="0.6.1")
    manifest_path = payload / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hooks"] = 42
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = reconciler.reconcile(root=cache, state_path=state)

    assert not report.ok
    assert any("malformed `hooks` entry" in problem for problem in report.problems)


def test_reconcile_accepts_wrapped_inline_mcp_tool_hook_declarations(
    cache: Path, state: Path
) -> None:
    """Bundled plugins may put the complete hooks.json shape inline in their manifest."""
    import _codex_hook_cache_payload as payloads

    payload = write_payload(root=cache, version="0.6.1")
    manifest_path = payload / ".codex-plugin" / "plugin.json"
    inline_hooks = {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "mcp_tool", "server": "node_repl", "tool": "turn_ended"}]}
            ],
            "Interrupt": [
                {"hooks": [{"type": "mcp_tool", "server": "node_repl", "tool": "turn_interrupted"}]}
            ],
            "SubagentStop": [
                {"hooks": [{"type": "mcp_tool", "server": "node_repl", "tool": "subagent_ended"}]}
            ],
        }
    }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hooks"] = inline_hooks
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (payload / "hooks" / "hooks.json").unlink()

    registrations, problems = payloads.hook_registrations(payload=payload)
    scripts, entrypoint_problems = reconciler.declared_hook_scripts(payload=payload)
    report = reconciler.reconcile(root=cache, state_path=state)

    assert not problems
    assert [(path, sorted(events)) for path, events in registrations] == [
        (manifest_path, ["Interrupt", "Stop", "SubagentStop"])
    ]
    assert scripts == ()
    assert not entrypoint_problems
    assert report.ok


def test_reconcile_output_names_wrapped_inline_non_command_hook_declarations(
    cache: Path, state: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Successful output identifies inline MCP hooks that need no path validation."""
    payload = write_payload(root=cache, version="0.6.1")
    manifest_path = payload / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hooks"] = {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "mcp_tool", "server": "node_repl", "tool": "turn_ended"}]}
            ],
            "Interrupt": [
                {"hooks": [{"type": "mcp_tool", "server": "node_repl", "tool": "turn_interrupted"}]}
            ],
            "SubagentStop": [
                {"hooks": [{"type": "mcp_tool", "server": "node_repl", "tool": "subagent_ended"}]}
            ],
        }
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (payload / "hooks" / "hooks.json").unlink()

    assert reconciler.main(["--codex-home", str(cache.parents[3]), "--state", str(state)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["hook_declarations"] == [
        (
            "Stop: mcp_tool node_repl.turn_ended "
            "(registered; no entrypoint validation for non-command hook)"
        ),
        (
            "Interrupt: mcp_tool node_repl.turn_interrupted "
            "(registered; no entrypoint validation for non-command hook)"
        ),
        (
            "SubagentStop: mcp_tool node_repl.subagent_ended "
            "(registered; no entrypoint validation for non-command hook)"
        ),
    ]


def test_reconcile_rejects_a_missing_command_entrypoint_from_wrapped_inline_hooks(
    cache: Path, state: Path
) -> None:
    """Inline command declarations validate their plugin-root entrypoints."""
    payload = write_payload(root=cache, version="0.6.1")
    manifest_path = payload / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hooks"] = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/missing.py"',
                        }
                    ]
                }
            ]
        }
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (payload / "hooks" / "hooks.json").unlink()

    report = reconciler.reconcile(root=cache, state_path=state)

    assert not report.ok
    assert any(
        "hooks/missing.py" in problem and "is missing" in problem for problem in report.problems
    )


def test_status_all_is_healthy_for_mixed_inline_and_path_declared_plugins(tmp_path: Path) -> None:
    """An inline bundled plugin never makes a healthy path plugin report unhealthy."""
    home = tmp_path / "codex"
    (home / "config.toml").parent.mkdir()
    (home / "config.toml").write_text(
        "[marketplaces.openai-bundled]\n\n[marketplaces.market]\n", encoding="utf-8"
    )
    inline = write_payload(
        root=home / "plugins" / "cache" / "openai-bundled" / "browser", version="1.0.0"
    )
    path_declared = write_payload(
        root=home / "plugins" / "cache" / "market" / "path-plugin", version="1.0.0"
    )
    manifest_path = inline / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hooks"] = {
        "hooks": {
            "Stop": [{"hooks": [{"type": "mcp_tool", "server": "node_repl", "tool": "turn_ended"}]}]
        }
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (inline / "hooks" / "hooks.json").unlink()

    reports = reconciler.reconcile_all(home=home)
    for report in reports:
        status_path = observer.status_file(
            state_path=reconciler.state_file(
                marketplace=report.marketplace or "",
                plugin=report.plugin or "",
                codex_home_override=home,
            )
        )
        observer.write_status(path=status_path, pid=os.getpid(), last_error=None)

    assert {report.plugin for report in reports} == {"browser", "path-plugin"}
    assert all(report.ok for report in reports)
    assert path_declared.is_dir()
    assert observer.main(["status", "--all", "--codex-home", str(home)]) == 0


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


def _write_config(*, home: Path, marketplaces: tuple[str, ...]) -> None:
    """Write the small host configuration shape coverage discovery consumes."""
    home.mkdir(parents=True)
    lines = [f"[marketplaces.{name}]" for name in marketplaces]
    (home / "config.toml").write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def _write_default_only_payload(*, root: Path, version: str) -> None:
    """Make a default-registration-only payload with a shell hook command."""
    payload = write_payload(root=root, version=version)
    manifest_path = payload / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("hooks")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registration = json.loads((payload / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    registration["hooks"]["Stop"][0]["hooks"][0]["command"] = (
        'if true; then bash "${CLAUDE_PLUGIN_ROOT}/hooks/stop.py"; fi'
    )
    (payload / "hooks" / "hooks.json").write_text(json.dumps(registration), encoding="utf-8")


def _write_manifest_only_payload(*, root: Path, version: str) -> None:
    """Make a manifest-registration-only payload with no default registration."""
    payload = write_payload(root=root, version=version)
    (payload / "hooks" / "hooks.json").rename(payload / "hooks" / "manifest-hooks.json")
    manifest_path = payload / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hooks"] = "./hooks/manifest-hooks.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
