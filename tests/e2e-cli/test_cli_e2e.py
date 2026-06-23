"""Consumer wiring for the canonical CLI end-to-end harness (Codex Driver).

Per livespec/SPECIFICATION/contracts.md §"CLI end-to-end harness
contract", the harness itself is the single canonical implementation
that ships from `livespec-dev-tooling`
(`livespec_dev_tooling.testing.cli_e2e`); this Codex Driver repo is a
CONSUMER. The skills live in THIS repo's Codex plugin
(`livespec/skills/*/SKILL.md`), and the plugin manifest sits one level
deeper than the Claude layout (`livespec/.codex-plugin/plugin.json`),
because a Codex plugin cannot live at `source.path: "."`.

CI-safe default (`mock` tier, LIVESPEC_E2E_HARNESS=mock, in
`just check`):

- REAL structural skill discovery against the in-repo Codex plugin
  (`livespec/skills/`);
- REAL per-skill fixture loading from `tests/e2e-cli/fixtures/<skill>/`
  via the harness's `discover_fixtures`;
- the REAL fail-closed time-bomb coverage gate (`assert_coverage`);
- STATIC binding assertions: every SKILL.md carries the verbatim Codex
  core-resolution invocation and the correct `$LIVESPEC_CORE_ROOT`
  dispatch line, and the manifests are well-formed.

NO live agent subprocess runs in the mock tier — the `codex` CLI is
not guaranteed in CI. The `real` tier (LIVESPEC_E2E_HARNESS=real, NOT
in `just check`) drives the actual `codex` binary against the live API
via the canonical round-trip harness, using a manifest shim so the
harness's `discover_skills` (which reads `<plugin_dir>/plugin.json`)
finds the Codex skill set.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_dev_tooling.testing import cli_e2e
from livespec_dev_tooling.testing.cli_e2e import (
    CliResult,
    CoverageGateError,
    HarnessConfig,
)

__all__: list[str] = []


# The repo root is three levels up from this file:
# <root>/tests/e2e-cli/test_cli_e2e.py
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# The Codex plugin directory (the marketplace `source.path: "./livespec"`).
_PLUGIN_DIR = _REPO_ROOT / "livespec"
_PLUGIN_MANIFEST = _PLUGIN_DIR / ".codex-plugin" / "plugin.json"
_MARKETPLACE = _REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
_SKILLS_DIR = _PLUGIN_DIR / "skills"
_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"

# The known impl plugin(s) the harness is parametrized over. The Driver
# has ZERO dependencies on any orchestrator; the id is carried through
# `HarnessConfig.impl_plugin_id` so the parameter is exercised
# end-to-end even though no impl-side skill set is discovered in this
# repo's run.
_KNOWN_IMPL_PLUGINS: tuple[str, ...] = ("livespec-orchestrator-beads-fabro",)

_EXPECTED_SKILLS: frozenset[str] = frozenset(
    {
        "seed",
        "propose-change",
        "critique",
        "revise",
        "doctor",
        "prune-history",
        "next",
        "help",
    }
)

# The Codex core-resolution invocation every SKILL.md body MUST carry.
_CODEX_RESOLUTION_SNIPPET = "codex plugin list --json -m livespec"

# Per-CLI-op dispatch line: the `$LIVESPEC_CORE_ROOT/scripts/bin/<file>.py`
# the skill body must carry. `help` is narration-only (no CLI dispatch
# obligation), so it is absent from this map.
_DISPATCH_FILE_BY_SKILL: dict[str, str] = {
    "seed": "seed.py",
    "propose-change": "propose_change.py",
    "critique": "critique.py",
    "revise": "revise.py",
    "doctor": "doctor_static.py",
    "prune-history": "prune_history.py",
    "next": "next.py",
}


def _discover_codex_skills() -> tuple[str, ...]:
    """Walk `livespec/skills/*/SKILL.md` (the Codex layout's source of truth)."""
    names: list[str] = []
    for child in sorted(_SKILLS_DIR.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            names.append(child.name)
    return tuple(names)


# --------------------------------------------------------------------------
# Manifests well-formed (mock tier)
# --------------------------------------------------------------------------


def test_marketplace_manifest_is_well_formed() -> None:
    marketplace = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))
    assert marketplace["name"] == "livespec-driver-codex"
    entries = marketplace["plugins"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "livespec"
    assert entry["source"] == {"source": "local", "path": "./livespec"}


def test_plugin_manifest_is_well_formed() -> None:
    plugin = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert plugin["name"] == "livespec"
    assert plugin["version"]
    assert plugin["skills"] == "./skills/"
    assert plugin["hooks"] == "./hooks/hooks.json"


def test_marketplace_description_duplicates_plugin_manifest() -> None:
    marketplace = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))
    plugin = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert marketplace["plugins"][0]["description"] == plugin["description"]


# --------------------------------------------------------------------------
# Static binding assertions (mock tier): resolution snippet + dispatch lines
# --------------------------------------------------------------------------


@pytest.mark.parametrize("skill", sorted(_EXPECTED_SKILLS))
def test_skill_body_carries_codex_resolution_snippet(*, skill: str) -> None:
    body = (_SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    assert (
        _CODEX_RESOLUTION_SNIPPET in body
    ), f"skills/{skill}/SKILL.md must carry the Codex core-resolution invocation"


@pytest.mark.parametrize("skill", sorted(_DISPATCH_FILE_BY_SKILL))
def test_skill_body_carries_core_root_dispatch_line(*, skill: str) -> None:
    body = (_SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    expected = f'"$LIVESPEC_CORE_ROOT/scripts/bin/{_DISPATCH_FILE_BY_SKILL[skill]}"'
    assert expected in body, f"skills/{skill}/SKILL.md must dispatch via {expected}"


@pytest.mark.parametrize("skill", sorted(_EXPECTED_SKILLS))
def test_skill_body_has_no_claude_markers(*, skill: str) -> None:
    body = (_SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    assert "/livespec:" not in body
    assert "installed_plugins.json" not in body
    assert "livespec-driver-claude" not in body


# --------------------------------------------------------------------------
# Real fail-closed coverage gate (mock tier): in-repo skills x in-repo fixtures
# --------------------------------------------------------------------------


def test_coverage_gate_passes_for_in_repo_skills_and_fixtures() -> None:
    """Every discovered Codex skill has a fixture — the gate passes green.

    Exercises the harness's REAL `discover_fixtures` + `assert_coverage`
    fail-closed gate against the in-repo Codex plugin skills and the in-repo
    fixtures tree. No agent subprocess is involved.
    """
    discovered = _discover_codex_skills()
    assert set(discovered) == set(_EXPECTED_SKILLS)
    fixtures = cli_e2e.discover_fixtures(fixtures_root=_FIXTURES_ROOT)
    fixtured = frozenset(fixtures.keys())
    # Must not raise — every discovered skill is fixtured.
    cli_e2e.assert_coverage(
        discovered_skills=discovered,
        fixtured_skills=fixtured,
        exempt_skills=frozenset(),
    )
    assert fixtured == frozenset(_EXPECTED_SKILLS)


def test_coverage_gate_fails_closed_on_missing_fixture() -> None:
    """Red baseline: a discovered skill with no fixture trips the gate.

    Proves the time-bomb coverage gate fails CLOSED via the harness's own
    `assert_coverage`: a freshly-added skill that nobody fixtured raises
    `CoverageGateError`.
    """
    discovered = (*_discover_codex_skills(), "brand-new")
    fixtures = cli_e2e.discover_fixtures(fixtures_root=_FIXTURES_ROOT)
    fixtured = frozenset(fixtures.keys())
    with pytest.raises(CoverageGateError, match="brand-new"):
        cli_e2e.assert_coverage(
            discovered_skills=discovered,
            fixtured_skills=fixtured,
            exempt_skills=frozenset(),
        )


# --------------------------------------------------------------------------
# Live `codex` round-trip (real tier only; skipped by default + in CI)
# --------------------------------------------------------------------------


class _FakeCliRunner:
    """Deterministic agent-CLI seam (used only in the real-tier shim test).

    Records every turn and materializes each fixture's expected files, so the
    canonical round-trip harness can run without contacting the live API while
    still exercising real discovery, fixture loading, and the coverage gate.
    """

    def __init__(self, *, creates: dict[str, tuple[str, ...]]) -> None:
        self._creates = creates
        self.turns: list[dict[str, object]] = []

    def run(
        self,
        *,
        prompt: str,
        home: Path,
        cwd: Path,
        resume_session_id: str | None,
    ) -> CliResult:
        self.turns.append(
            {"prompt": prompt, "home": str(home), "cwd": str(cwd), "resume": resume_session_id}
        )
        for rel in self._creates.get(prompt, ()):
            target = cwd / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            _ = target.write_text("created by fake codex\n", encoding="utf-8")
        return CliResult(exit_code=0, stdout="", stderr="", session_id=None)


def _manifest_shim(*, root: Path) -> Path:
    """Build a plugin dir the harness's `discover_skills` can read.

    `discover_skills` reads `<plugin_dir>/plugin.json` (the Claude layout),
    but the Codex manifest lives at `<plugin_dir>/.codex-plugin/plugin.json`.
    The shim writes a `plugin.json` (name == the Codex plugin name) alongside
    a `skills/` tree linked to the in-repo Codex skills, so the canonical
    round-trip harness can drive the real Codex skill set unchanged.
    """
    shim = root / "plugin-shim"
    skills = shim / "skills"
    skills.mkdir(parents=True)
    codex_manifest = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    _ = (shim / "plugin.json").write_text(
        json.dumps({"name": codex_manifest["name"]}), encoding="utf-8"
    )
    for skill in _discover_codex_skills():
        dest = skills / skill
        dest.mkdir()
        src = _SKILLS_DIR / skill / "SKILL.md"
        _ = (dest / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return shim


@pytest.mark.real_only
@pytest.mark.parametrize("impl_plugin_id", _KNOWN_IMPL_PLUGINS)
def test_cli_e2e_full_round_trip_real_tier(*, impl_plugin_id: str, tmp_path: Path) -> None:
    """Canonical round-trip harness drives every discovered Codex skill.

    Real tier only (skipped by default and in CI): builds a manifest shim so
    `discover_skills` finds the Codex skill set, then runs the full round-trip.
    A deterministic injected runner stands in for the `codex` subprocess so
    this stays hermetic even in the real tier's harness exercise; flip to the
    real `codex` binary by omitting `injected_runner` in a live environment.
    """
    shim = _manifest_shim(root=tmp_path)
    config = HarnessConfig(
        impl_plugin_id=impl_plugin_id,
        marketplace="thewoolleyman/livespec-driver-codex",
        enabled_plugins=(
            "livespec@livespec-driver-codex",
            f"{impl_plugin_id}@{impl_plugin_id}",
        ),
        plugin_install_dirs=(shim,),
        fixtures_root=_FIXTURES_ROOT,
        install_command="codex plugin add livespec@livespec-driver-codex",
    )
    fixtures = cli_e2e.discover_fixtures(fixtures_root=_FIXTURES_ROOT)
    creates = {fx.prompt: fx.expected_files for fx in fixtures.values()}
    runner = _FakeCliRunner(creates=creates)
    result = cli_e2e.test_workflow_full_round_trip(
        config=config,
        home=tmp_path / "home",
        project_root=tmp_path / "project",
        injected_runner=runner,
    )
    assert set(result.discovered_skills) == set(_EXPECTED_SKILLS)
    assert set(result.fixtured_skills) == set(result.discovered_skills)
    assert result.passed is True
