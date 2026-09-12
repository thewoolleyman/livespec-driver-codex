"""Conformance witnesses for the Driver's structural and operational spec rows.

Each test asserts a concrete, control-armed fact about THIS repo that a
spec heading commits to: the three shipped Codex mechanics exist, the
declared repo layout is present, the enforcement-suite gates are wired,
the test surfaces exist, the version source-of-truth holds, and the
heading-coverage check-runner (the mechanical teeth behind spec evolution)
runs clean here and reddens on an uncovered heading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_dev_tooling.checks import heading_coverage

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_purpose_ships_the_three_codex_mechanics() -> None:
    """spec.md "Purpose": the repo ships exactly three Codex-runtime things.

    (1) the eight thin SKILL.md bindings, (2) the plugin-shipped hook bundle,
    (3) the structural gate. Control-armed: a missing binding, hooks.json, or
    the gate script fails here.
    """
    skills = _REPO_ROOT / "livespec" / "skills"
    for name in (
        "seed",
        "propose-change",
        "critique",
        "revise",
        "doctor",
        "prune-history",
        "next",
        "help",
    ):
        assert (skills / name / "SKILL.md").is_file()
    assert (_REPO_ROOT / "livespec" / "hooks" / "hooks.json").is_file()
    assert (_REPO_ROOT / "livespec" / "hooks" / "livespec_footgun_guard.py").is_file()
    # The structural gate now ships from the shared dev-tooling package and is
    # wired as `check-plugin-structure`; the spec's literal
    # `dev-tooling/check_plugin_structure.py` path is stale drift.
    from livespec_dev_tooling.driver_checks import plugin_structure

    assert callable(plugin_structure.main)


def test_repo_layout_declared_paths_exist() -> None:
    """non-functional-requirements.md "Repo layout": every declared path exists."""
    for rel in (
        ".agents/plugins/marketplace.json",
        "livespec/.codex-plugin/plugin.json",
        "livespec/skills",
        "livespec/hooks/hooks.json",
        "dev-tooling/codex_hook_cache_reconcile.py",
        "dev-tooling/codex_hook_cache_observe.py",
        "tests/dev-tooling",
        "tests/e2e-cli",
        "tests/hooks",
        "SPECIFICATION",
        "justfile",
        "lefthook.yml",
        ".mise.toml",
        "pyproject.toml",
    ):
        assert (_REPO_ROOT / rel).exists(), rel


def test_enforcement_suite_gates_are_wired() -> None:
    """non-functional-requirements.md "Enforcement suite": each named gate is a recipe."""
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    for gate in (
        "check-plugin-structure",
        "check-hooks",
        "check-e2e-cli",
        "check-codex-skill-picker",
        "check-dev-tooling",
        "check-heading-coverage",
        "check-lint",
        "check-format",
    ):
        assert f"\n{gate}:" in justfile, gate


def test_test_discipline_surfaces_exist() -> None:
    """non-functional-requirements.md "Test discipline": the three test surfaces are populated."""
    for surface in ("e2e-cli", "hooks", "dev-tooling"):
        directory = _REPO_ROOT / "tests" / surface
        assert directory.is_dir()
        assert list(directory.glob("test_*.py")), surface


def test_versioning_plugin_json_is_the_sole_version_source() -> None:
    """contracts.md "Versioning" + n-f-r "Build and release": version SoT.

    `plugin.json.version` is non-empty (release-please auto-manages it) and
    `marketplace.json` carries NO `version` field. Control-armed: either an
    empty plugin version or a version key on the marketplace fails here.
    """
    plugin = json.loads(
        (_REPO_ROOT / "livespec" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert plugin.get("version"), plugin.get("version")
    marketplace = json.loads(
        (_REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert "version" not in marketplace


def test_spec_evolution_heading_coverage_runs_clean_and_catches_an_uncovered_heading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """non-functional-requirements.md "Spec evolution": the heading-coverage gate.

    check-heading-coverage mechanically keeps the spec's H2 set in lockstep
    with tests/heading-coverage.json. This runs the real check-runner against
    THIS repo (clean, exit 0) and against a fixture spec tree with an
    uncovered heading (reddens, exit 1).
    """
    monkeypatch.chdir(_REPO_ROOT)
    assert heading_coverage.main() == 0

    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    (spec / "spec.md").write_text("# T\n\n## Uncovered heading\n\nbody\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "heading-coverage.json").write_text("[]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert heading_coverage.main() == 1
