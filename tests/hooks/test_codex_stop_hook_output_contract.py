"""Every declared Codex Stop hook's non-empty stdout, validated against the contract.

The incident this closes: a Stop hook emitted a PreToolUse-style
`hookSpecificOutput` deny object and the Codex Stop runtime rejected it. Each
hook's own suite asserted parseability and `decision == "block"` — properties
that broken payload satisfied — so nothing failed until release.

Two properties are asserted here, and it takes both to keep the seam shut:

- COMPLETENESS — every script `hooks/hooks.json` declares under `Stop` has a
  scenario that drives it to a non-empty payload. A fourth Stop hook added
  without one fails this test instead of shipping unvalidated.
- CONFORMANCE — each of those payloads validates through
  `codex_stop_output_contract.validate_stop_output`, the single versioned
  transcription of the Codex CLI Stop-output schema.

The hooks run IN-PROCESS here, the way their per-hook suites run them.
`test_shipped_hooks_install_shape.py` runs the SAME scenarios as subprocesses
out of a copied plugin cache, where nothing above `livespec/` exists.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest
from returns.result import Success

from .codex_stop_output_contract import validate_stop_output
from .codex_stop_scenarios import (
    STOP_SCENARIO_LABELS,
    StopScenario,
    build_stop_scenarios,
    declared_stop_hook_scripts,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
_HOOKS_JSON = _HOOKS_DIR / "hooks.json"

# Every environment variable a scenario may set, cleared before each run so an
# ambient value from the developer's own session cannot decide the payload.
_SCENARIO_ENV_KEYS = ("CLAUDE_PROJECT_DIR", "LIVESPEC_CODEX_BACKGROUND_MEMORY_DB")


def _load_hook(*, script: str):
    """Import one shipped hook under a private module name.

    The hooks resolve their sibling imports (`_result`, `_supervisor_producers`)
    through their own directory on `sys.path`, exactly as they do when Codex runs
    them. The module name is suffixed so re-importing a hook here never displaces
    the instance another suite in this session already holds.
    """
    assert (_HOOKS_DIR / script).is_file(), f"{script} must be shipped"
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    name = f"{script.removesuffix('.py')}_stop_contract"
    spec = importlib.util.spec_from_file_location(name, str(_HOOKS_DIR / script))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run_stop_hook(*, scenario: StopScenario) -> str:
    """Run the scenario's hook in-process and return its stdout."""
    module = _load_hook(script=scenario.script)
    stdout = io.StringIO()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(scenario.cwd)
        for key in _SCENARIO_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        for key, value in scenario.env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(sys, "stdin", io.StringIO(scenario.stdin))
        monkeypatch.setattr(sys, "stdout", stdout)
        returncode = module.main()
    assert returncode == 0, f"{scenario.script} must exit 0"
    return stdout.getvalue()


@pytest.fixture(scope="module")
def stop_scenarios(tmp_path_factory: pytest.TempPathFactory) -> dict[str, StopScenario]:
    return build_stop_scenarios(root=tmp_path_factory.mktemp("codex-stop-scenarios"))


def test_every_declared_stop_hook_has_a_non_empty_payload_scenario(
    stop_scenarios: dict[str, StopScenario],
) -> None:
    """A Stop hook with no payload scenario is a Stop hook nothing contract-checks."""
    covered = {scenario.script for scenario in stop_scenarios.values()}

    assert covered == set(declared_stop_hook_scripts(hooks_json=_HOOKS_JSON))


@pytest.mark.parametrize("label", STOP_SCENARIO_LABELS)
def test_declared_stop_hook_payloads_satisfy_the_codex_contract(
    stop_scenarios: dict[str, StopScenario],
    label: str,
) -> None:
    scenario = stop_scenarios[label]

    output = _run_stop_hook(scenario=scenario)

    assert output.strip(), f"{label}: expected a non-empty Stop payload"
    validated = validate_stop_output(output=output)
    assert isinstance(validated, Success), f"{label}: {validated}"
    assert set(validated.unwrap()) == set(scenario.expected_keys)
