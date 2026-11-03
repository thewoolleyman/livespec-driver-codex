"""Integration witnesses for the Bash PreToolUse dispatcher scenario."""

from __future__ import annotations

import json
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_JSON = _REPO_ROOT / "livespec" / "hooks" / "hooks.json"
_COVERAGE = _REPO_ROOT / "tests" / "heading-coverage.json"
_HEADING = (
    "## Scenario: one Bash tool call starts one Python process for the Driver's PreToolUse guards"
)
_TEST_ID = (
    "tests.integration.test_pretooluse_dispatch_scenarios."
    "test_bash_call_starts_one_dispatcher_process"
)


def _bash_commands() -> list[str]:
    declared = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    entries = [
        entry
        for entry in declared["hooks"]["PreToolUse"]
        if entry.get("matcher") == "Bash"
    ]
    return [hook["command"] for entry in entries for hook in entry["hooks"]]


def _coverage_test_id() -> str:
    rows = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    return next(
        row["test"]
        for row in rows
        if row["spec_file"] == "scenarios.md" and row["heading"] == _HEADING
    )


def test_bash_call_starts_one_dispatcher_process() -> None:
    """The sole Bash hook command starts the dispatcher, not each guard."""
    assert _bash_commands() == ['python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_dispatch.py"']


def test_single_process_scenario_is_bound_to_integration_witness() -> None:
    """The scenario registry names this integration witness rather than TODO."""
    assert _coverage_test_id() == _TEST_ID
