"""Unit tests for `livespec/hooks/block_raw_bd_create.py`.

The hook body is exercised IN-PROCESS via its importable `main() -> int`
(monkeypatched `sys.stdin` + `CLAUDE_PROJECT_DIR`, stdout via `capsys`) for
real per-file coverage. The install-shaped subprocess proof that the shipped
script still starts under bare `python3` lives in
`test_shipped_hooks_install_shape.py`, so nothing here spawns a process.

This body is shipped BYTE-IDENTICALLY by both Drivers (livespec-driver-claude
at `.claude-plugin/hooks/`, livespec-driver-codex at `livespec/hooks/`) because
Codex consumes the Claude PreToolUse hook I/O format; this test pins its
contract on the Codex side.

Contract under test (work-item livespec-driver-codex-tuwox2, mirroring
livespec-driver-claude-wgufs2):

- A raw `bd create` Bash invocation in a livespec-governed project (a
  `.livespec.jsonc` declaring `implementation.plugin`) is DENIED with decision
  JSON whose reason routes the intake to the resolved
  `/<plugin>:capture-work-item` operation — the namespace comes from config,
  never hardcoded — and cites the two surfaces that already go loud about a
  stranded item rather than adding a third.
- Every other Bash invocation passes through unchanged, including one that
  merely MENTIONS `bd create` as quoted data.
- Everything else — non-Bash tools, non-governed projects, unset
  CLAUDE_PROJECT_DIR, malformed stdin — is a silent pass-through: exit 0,
  empty stdout (fail-open).

Every corpus command below is INERT DATA fed to the hook on stdin. Nothing
here runs `bd`, and nothing may be changed to do so.
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOK_SCRIPT = _REPO_ROOT / "livespec" / "hooks" / "block_raw_bd_create.py"
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import block_raw_bd_create  # noqa: E402 — path-dependent hook import.

# Invocations that file a work-item at the beads-native `open` status, outside
# the livespec status vocabulary — the intake failure this hook prevents.
_DENY_COMMANDS = (
    "bd create",
    "bd create -t 'PreToolUse guard on raw bd create'",
    "bd create --type task --priority 1 -t x",
)


def _hook_input(*, command: str, tool_name: str = "Bash") -> str:
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
        }
    )


def _governed_project(*, root: Path, plugin: str = "livespec-orchestrator-beads-fabro") -> Path:
    """Materialize a livespec-governed project with a commented JSONC config."""
    config = (
        "// Project-local livespec configuration (JSONC: comments are legal).\n"
        "{\n"
        '  "template": "livespec",\n'
        f'  "implementation": {{ "plugin": "{plugin}" }}\n'
        "}\n"
    )
    _ = (root / ".livespec.jsonc").write_text(config, encoding="utf-8")
    return root


def _run(*, monkeypatch, capsys, stdin: str, project_dir: Path | None) -> tuple[int, str]:
    """Drive `main()` in-process; return (returncode, stdout)."""
    monkeypatch.setattr(sys, "stdin", StringIO(stdin))
    if project_dir is None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    else:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_dir))
    returncode = block_raw_bd_create.main()
    captured = capsys.readouterr()
    assert captured.err == ""
    return returncode, captured.out


def _assert_pass_through(*, returncode: int, stdout: str) -> None:
    assert returncode == 0
    assert stdout == ""


def test_hook_script_is_shipped() -> None:
    assert _HOOK_SCRIPT.is_file()


@pytest.mark.parametrize("command", _DENY_COMMANDS)
def test_denies_raw_bd_create_in_governed_project(
    monkeypatch, capsys, tmp_path: Path, command: str
) -> None:
    project = _governed_project(root=tmp_path)
    returncode, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin=_hook_input(command=command),
        project_dir=project,
    )
    assert returncode == 0
    assert stdout, f"the raw create reached the shell unredirected: {command!r}"
    decision = json.loads(stdout)
    assert decision["decision"] == "block"
    assert decision["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert decision["hookSpecificOutput"]["permissionDecisionReason"] == decision["reason"]
    assert "/livespec-orchestrator-beads-fabro:capture-work-item" in decision["reason"]


def test_reason_routes_intake_and_cites_the_existing_loud_surfaces(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    """The redirect explains the intake failure and points at the two loud surfaces."""
    project = _governed_project(root=tmp_path)
    _, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin=_hook_input(command="bd create -t x"),
        project_dir=project,
    )
    decision = json.loads(stdout)
    reason = decision["reason"]
    assert "/livespec-orchestrator-beads-fabro:capture-work-item" in reason
    assert "Definition-of-Ready" in reason
    assert "work_item_status_vocabulary" in reason
    assert "untriaged_backlog_items" in reason
    assert decision["hookSpecificOutput"]["permissionDecisionReason"] == reason


def test_reason_names_the_configured_plugin_namespace(monkeypatch, capsys, tmp_path: Path) -> None:
    project = _governed_project(root=tmp_path, plugin="livespec-impl-plaintext")
    _, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin=_hook_input(command="bd create -t x"),
        project_dir=project,
    )
    decision = json.loads(stdout)
    assert "/livespec-impl-plaintext:capture-work-item" in decision["reason"]
    assert "/livespec-orchestrator-beads-fabro" not in decision["reason"]


def test_passes_through_in_ungoverned_project(monkeypatch, capsys, tmp_path: Path) -> None:
    returncode, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin=_hook_input(command="bd create -t x"),
        project_dir=tmp_path,
    )
    _assert_pass_through(returncode=returncode, stdout=stdout)


def test_passes_through_when_project_dir_unset(monkeypatch, capsys, tmp_path: Path) -> None:
    _governed_project(root=tmp_path)
    returncode, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin=_hook_input(command="bd create -t x"),
        project_dir=None,
    )
    _assert_pass_through(returncode=returncode, stdout=stdout)


def test_passes_through_for_non_bash_tool(monkeypatch, capsys, tmp_path: Path) -> None:
    project = _governed_project(root=tmp_path)
    returncode, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin=_hook_input(command="bd create -t x", tool_name="Write"),
        project_dir=project,
    )
    _assert_pass_through(returncode=returncode, stdout=stdout)


def test_passes_through_when_tool_input_missing(monkeypatch, capsys, tmp_path: Path) -> None:
    project = _governed_project(root=tmp_path)
    returncode, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin=json.dumps({"tool_name": "Bash"}),
        project_dir=project,
    )
    _assert_pass_through(returncode=returncode, stdout=stdout)


def test_passes_through_when_command_missing_or_empty(monkeypatch, capsys, tmp_path: Path) -> None:
    project = _governed_project(root=tmp_path)
    for tool_input in ({"timeout": 30}, {"command": ""}):
        returncode, stdout = _run(
            monkeypatch=monkeypatch,
            capsys=capsys,
            stdin=json.dumps({"tool_name": "Bash", "tool_input": tool_input}),
            project_dir=project,
        )
        _assert_pass_through(returncode=returncode, stdout=stdout)


def test_passes_through_on_malformed_stdin(monkeypatch, capsys, tmp_path: Path) -> None:
    project = _governed_project(root=tmp_path)
    returncode, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin="not json at all",
        project_dir=project,
    )
    _assert_pass_through(returncode=returncode, stdout=stdout)


def test_passes_through_on_non_mapping_payload(monkeypatch, capsys, tmp_path: Path) -> None:
    project = _governed_project(root=tmp_path)
    returncode, stdout = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        stdin="[]",
        project_dir=project,
    )
    _assert_pass_through(returncode=returncode, stdout=stdout)


def test_main_fails_open_when_the_decision_rail_raises(monkeypatch, capsys) -> None:
    """The boundary catch owns an UNEXPECTED failure: still exit 0, still silent."""

    def broken_decision(*, raw: str):
        raise RuntimeError(raw)

    monkeypatch.setattr(block_raw_bd_create.sys, "stdin", StringIO("{}"))
    monkeypatch.setattr(block_raw_bd_create, "_decision_result", broken_decision)
    assert block_raw_bd_create.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
