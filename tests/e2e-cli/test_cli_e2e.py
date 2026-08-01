"""Consumer wiring for the canonical CLI end-to-end harness (Codex Driver).

Per livespec/SPECIFICATION/contracts.md, the harness itself is the single canonical implementation
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
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_dev_tooling.testing import cli_e2e
from livespec_dev_tooling.testing.cli_e2e import (
    CliResult,
    CoverageGateError,
    FixturedSkill,
    HarnessConfig,
)

_VENDOR_DIR = Path(cli_e2e.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.primitives.exceptions import (  # noqa: E402  — vendor-path-aware import.
    UnwrapFailedError,
)
from returns.result import Failure, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []


def _round_trip_result(outcome: object) -> cli_e2e.WorkflowResult:
    """Normalize BOTH harness return shapes so the dev-tooling pin can move either way.

    Through `v1.0.x`, `test_workflow_full_round_trip` RAISED `WorkflowFailedError`
    on a failing step and returned a bare `WorkflowResult`. After the ROP
    conversion in dev-tooling it returns a `Result[WorkflowResult, ...]` instead.

    *** THE FAILURE THIS EXISTS TO PREVENT IS SILENT. *** A `Failure` is TRUTHY and
    carries no `.passed`, so a wrapper written for the old shape does NOT blow up
    against the new one — it simply STOPS CHECKING, and this suite goes GREEN on a
    broken round trip. That is `livespec-dev-tooling-dx8l`'s failure mode aimed at
    a test gate: the guard does not fail, it stops being a guard.

    Accepting BOTH shapes satisfies "consumer wiring lands before the change that
    assumes it" for EVERY pin version at once, so the pin can move in either
    direction — forward to the conversion or back on a revert — without re-breaking.

    Duck-typed on purpose: the helper must not depend on dev-tooling's vendored
    `returns` layout at call time, since it has to work across pin versions on
    both sides of the conversion. The tests below pin the REAL `Success`/`Failure`
    shapes, so the tolerance is proven rather than assumed.
    """
    if isinstance(outcome, cli_e2e.WorkflowResult):
        return outcome  # pre-conversion shape; a failing step would already have raised
    unwrap = getattr(outcome, "unwrap", None)
    assert unwrap is not None, (
        f"unexpected harness return shape {type(outcome).__name__}; "
        "expected a WorkflowResult or a returns Result"
    )
    # `.unwrap()` RAISES on a Failure, so a failed round trip fails this test LOUDLY
    # rather than passing silently. Asserting on the unwrapped VALUE is the point:
    # proving the call succeeded is exactly what the silent-pass bug also does.
    unwrapped = unwrap()
    assert isinstance(
        unwrapped, cli_e2e.WorkflowResult
    ), f"harness Result carried {type(unwrapped).__name__}, not a WorkflowResult"
    return unwrapped


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


def _returning(*, shape: object) -> Callable[..., object]:
    """A `discover_fixtures` stand-in handing back exactly `shape`."""

    def _call(**_kwargs: object) -> object:
        return shape

    return _call


def _discovered_fixtures(*, fixtures_root: Path) -> dict[str, FixturedSkill]:
    """The harness's fixtures, from EITHER shape of `discover_fixtures`.

    CONSUMER WIRING LANDS BEFORE THE PIN THAT NEEDS IT (livespec
    `.ai/ci-gate-discipline.md` step 3, and `livespec-dev-tooling-dx8l`). Up to
    dev-tooling v1.13.15 `discover_fixtures` returns a bare
    `dict[str, FixturedSkill]`; the `livespec-dev-tooling-8o8e` railway
    conversion returns a `returns` container over that dict, because today an
    unreadable `prompt.md` raises straight out of it and an unreadable fixtures
    root yields `{}` — "no fixtures" — which the fail-closed coverage gate then
    passes VACUOUSLY. Accepting both shapes is what lets that pin move in
    EITHER direction, a revert included, without reddening this repo's master.

    ⛔ WHY `.map()` AND NOT `.unwrap()`, because the sibling `_round_trip_result`
    helper uses the latter and copying it here is wrong one container deep:
    `.unwrap()` is correct for the `Result` that helper consumes, but
    `IOResult.unwrap()` yields an `IO[dict]`, NOT a dict. `frozenset(IO(...))`
    then raises, and `.values()` does not exist on it; wiring that instead fell
    back to `{}` would feed an EMPTY fixture set to `assert_coverage`, which
    computes `discovered - fixtured - exempt` and would report the gate
    SATISFIED. `.map()` is uniform across both containers, runs ONLY on the
    success track, and needs no import of the railway library.

    This repo has THREE call sites — two feeding `assert_coverage` directly —
    so it is the one where a silently empty fixture set does the most damage.
    """
    discovered = cli_e2e.discover_fixtures(fixtures_root=fixtures_root)
    if isinstance(discovered, dict):
        return discovered
    unwrapped: list[dict[str, FixturedSkill]] = []
    _ = discovered.map(unwrapped.append)
    assert unwrapped, f"discover_fixtures could not read {fixtures_root}: {discovered!r}"
    return unwrapped[0]


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
    fixtures = _discovered_fixtures(fixtures_root=_FIXTURES_ROOT)
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
    fixtures = _discovered_fixtures(fixtures_root=_FIXTURES_ROOT)
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
    fixtures = _discovered_fixtures(fixtures_root=_FIXTURES_ROOT)
    creates = {fx.prompt: fx.expected_files for fx in fixtures.values()}
    runner = _FakeCliRunner(creates=creates)
    result = _round_trip_result(
        cli_e2e.test_workflow_full_round_trip(
            config=config,
            home=tmp_path / "home",
            project_root=tmp_path / "project",
            injected_runner=runner,
        )
    )
    assert set(result.discovered_skills) == set(_EXPECTED_SKILLS)
    assert set(result.fixtured_skills) == set(result.discovered_skills)
    assert result.passed is True


def test_round_trip_result_accepts_the_pre_conversion_shape() -> None:
    """A bare `WorkflowResult` passes straight through — the shape today's pin returns."""
    result = cli_e2e.WorkflowResult(discovered_skills=("seed",), fixtured_skills=("seed",))

    assert _round_trip_result(result) is result


def test_round_trip_result_unwraps_the_post_conversion_success_to_its_value() -> None:
    """A `Success` yields the WorkflowResult ITSELF, not the container.

    Asserting on the VALUE is the whole point. `frozenset(IOResult.unwrap())`
    silently yielding a set holding the wrapper — the bug that shipped in
    dev-tooling's own conversion — passes any test that only checks the call
    succeeded. A wrapper reaching the caller in place of its payload is exactly
    what this class of bug produces.
    """
    result = cli_e2e.WorkflowResult(discovered_skills=("seed",), fixtured_skills=("seed",))

    unwrapped = _round_trip_result(Success(result))

    assert unwrapped is result
    assert isinstance(unwrapped, cli_e2e.WorkflowResult)
    assert unwrapped.discovered_skills == ("seed",)


def test_round_trip_result_fails_loudly_on_the_post_conversion_failure() -> None:
    """A `Failure` RAISES rather than passing.

    This is the assertion the whole helper exists for. A `Failure` is TRUTHY and
    has no `.passed`, so wiring written for the old shape would neither raise nor
    check — this suite would go green on a broken round trip.
    """
    with pytest.raises(UnwrapFailedError):
        _ = _round_trip_result(Failure(RuntimeError("two skills failed")))


def _fixture(*, skill: str) -> FixturedSkill:
    return FixturedSkill(skill=skill, prompt=f"drive {skill}", expected_files=())


def test_discovered_fixtures_accepts_every_harness_shape(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dual-shape tolerance, PROVEN against real containers rather than assumed.

    Three shapes, because the pin must be free to move in either direction and
    the conversion's container type is dev-tooling's choice, not this repo's:
    the current bare `dict`, and the success track of both `Result` and
    `IOResult`.

    ⛔ THE `IOSuccess` CASE IS THE LOAD-BEARING ONE. The sibling
    `_round_trip_result` helper normalizes with `.unwrap()`, which is correct
    for the `Result` it consumes — but `IOResult.unwrap()` yields an `IO[dict]`,
    NOT a dict. Reusing that idiom at this file's three call sites would break
    `frozenset(fixtures.keys())` outright, and wiring that fell back to `{}`
    instead would hand `assert_coverage` an EMPTY fixture set. `.map()` is
    uniform across both containers, which is why it is used.
    """
    fixtures = {"seed": _fixture(skill="seed")}

    for shape in (fixtures, Success(fixtures), IOSuccess(fixtures)):
        monkeypatch.setattr(cli_e2e, "discover_fixtures", _returning(shape=shape))

        assert (
            _discovered_fixtures(fixtures_root=tmp_path) == fixtures
        ), f"shape {type(shape).__name__} must normalize to the bare mapping"


def test_discovered_fixtures_fails_loudly_on_an_unreadable_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure track must FAIL, never degrade to "no fixtures".

    The positive control, and the half that carries the value. Without it,
    wiring that quietly returned `{}` on the failure track would satisfy every
    assertion above while feeding an EMPTY fixture set to the fail-closed
    coverage gate — which then computes `discovered - fixtured - exempt` over
    nothing and PASSES. That is this epic's exact subject: a gate reporting
    success because the thing it measures never happened, and this file wires
    that gate twice.
    """
    for shape in (Failure("unreadable"), IOFailure("unreadable")):
        monkeypatch.setattr(cli_e2e, "discover_fixtures", _returning(shape=shape))

        with pytest.raises(AssertionError):
            _ = _discovered_fixtures(fixtures_root=tmp_path)
