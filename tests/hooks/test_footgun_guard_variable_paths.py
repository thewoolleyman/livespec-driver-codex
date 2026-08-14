"""Variable-target regression controls for the shipped Codex footgun guard."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import livespec_footgun_guard  # noqa: E402 — path-dependent hook import.


def _primary_git_repo(*, root: Path) -> Path:
    subprocess.run(
        ["git", "init", "--quiet", str(root)], check=True, capture_output=True, text=True
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "livespec.primaryPath", str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    return root


def _decision(*, command: str, cwd: Path) -> str | None:
    old_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        result = livespec_footgun_guard._decision(
            raw=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        )
    finally:
        os.chdir(old_cwd)
    return result.unwrap()


@pytest.mark.parametrize(
    "relative_target",
    ["tracked.txt", "tmp/overseer/status.log"],
)
def test_denies_literal_variable_outside_supervisor_runtime_subtree(
    tmp_path: Path, relative_target: str
) -> None:
    primary = _primary_git_repo(root=tmp_path / "primary")
    _ = (primary / ".gitignore").write_text("tmp/\n", encoding="utf-8")
    target = primary / relative_target
    decision = _decision(command=f'output="{target}"; echo blocked > "$output"', cwd=primary)
    assert decision is not None
