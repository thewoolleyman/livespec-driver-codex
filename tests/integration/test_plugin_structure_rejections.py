"""Control-armed integration coverage for the Codex Driver structural check.

Each test copies this repo's shipped Codex plugin tree (`livespec/` +
`.agents/`) into an isolated fixture, confirms the pristine copy passes
`codex_profile_violations`, then mutates exactly one thing to inject the
violation named by the mapped spec scenario and asserts the check
convicts it. The clean-tree assertion is the control arm: it proves a
conviction below is attributable to the injected defect rather than to a
tree that never passed. These witness the "structural check rejects ..."
scenarios in SPECIFICATION/scenarios.md and the binding rules they
enforce in SPECIFICATION/contracts.md and SPECIFICATION/constraints.md.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from livespec_dev_tooling.checks import no_direct_tool_invocation
from livespec_dev_tooling.driver_checks.plugin_structure import codex_profile_violations
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _violations(*, root: Path) -> list[str]:
    outcome = codex_profile_violations(root=root)
    assert isinstance(outcome, IOSuccess), outcome
    return list(unsafe_perform_io(outcome.unwrap()))


@pytest.fixture
def codex_tree(tmp_path: Path) -> Path:
    """A byte copy of the shipped Codex plugin tree that passes the check clean."""
    root = tmp_path / "tree"
    root.mkdir()
    shutil.copytree(_REPO_ROOT / "livespec", root / "livespec")
    shutil.copytree(_REPO_ROOT / ".agents", root / ".agents")
    assert _violations(root=root) == [], "shipped tree must pass before any mutation"
    return root


def test_real_codex_tree_passes_structural_check(codex_tree: Path) -> None:
    """The pristine copy passing IS the control arm for every rejection below."""
    assert _violations(root=codex_tree) == []


def test_structural_check_rejects_skill_md_invoking_uv_run(codex_tree: Path) -> None:
    skill_md = codex_tree / "livespec" / "skills" / "seed" / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8")
        + '\n```bash\nuv run python3 "$LIVESPEC_CORE_ROOT/scripts/bin/seed.py"\n```\n',
        encoding="utf-8",
    )
    assert any("uses 'uv run'" in v for v in _violations(root=codex_tree))


def test_structural_check_rejects_driver_plugin_root_placeholder(codex_tree: Path) -> None:
    # The banned Driver placeholder is assembled at runtime so this test file
    # never contains the literal token the checker greps for.
    placeholder = "${" + "CLAUDE_PLUGIN" + "_ROOT}"
    skill_md = codex_tree / "livespec" / "skills" / "seed" / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8")
        + f'\n```bash\npython3 "{placeholder}/scripts/bin/seed.py"\n```\n',
        encoding="utf-8",
    )
    assert any("Driver's own plugin-root placeholder" in v for v in _violations(root=codex_tree))


def test_structural_check_rejects_extra_or_missing_skill_directory(codex_tree: Path) -> None:
    skills = codex_tree / "livespec" / "skills"
    shutil.rmtree(skills / "seed")
    (skills / "bogus").mkdir()
    found = _violations(root=codex_tree)
    assert any("missing skill directory: skills/seed/" in v for v in found)
    assert any("unexpected skill directory: skills/bogus/" in v for v in found)


def test_structural_check_rejects_binding_body_carrying_a_claude_marker(codex_tree: Path) -> None:
    skill_md = codex_tree / "livespec" / "skills" / "seed" / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\nThis is the Claude Code Driver.\n",
        encoding="utf-8",
    )
    assert any("Claude Code Driver" in v for v in _violations(root=codex_tree))


def test_structural_check_rejects_marketplace_description_drift(codex_tree: Path) -> None:
    import json

    manifest = codex_tree / "livespec" / ".codex-plugin" / "plugin.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["description"] = data.get("description", "") + " (drifted)"
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    assert any(
        "description MUST duplicate plugin.json's verbatim" in v
        for v in _violations(root=codex_tree)
    )


def test_structural_check_rejects_missing_hook_guard(codex_tree: Path) -> None:
    (codex_tree / "livespec" / "hooks" / "livespec_footgun_guard.py").unlink()
    assert any(
        "missing livespec/hooks/livespec_footgun_guard.py" in v
        for v in _violations(root=codex_tree)
    )


def test_task_runner_discipline_bans_direct_tool_invocation(monkeypatch, tmp_path: Path) -> None:
    """Witness non-functional-requirements.md "Task-runner discipline".

    lefthook.yml and CI YAML MUST route every dev-tool call through
    `just <target>`; check-no-direct-tool-invocation enforces it. The
    control arm drives the check to conviction on a fabricated lefthook
    hook that shells out to pytest directly.
    """
    monkeypatch.chdir(_REPO_ROOT)
    assert no_direct_tool_invocation.main() == 0

    violation = tmp_path / "violation"
    violation.mkdir()
    (violation / "lefthook.yml").write_text(
        "pre-push:\n  commands:\n    tests:\n      run: pytest -q\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(violation)
    assert no_direct_tool_invocation.main() == 1
