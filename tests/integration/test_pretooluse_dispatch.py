"""Integration witness for the Bash PreToolUse guard dispatcher."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOKS = _ROOT / "livespec" / "hooks"


def _payload(*, command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _run(*, script: str, raw: str, project_dir: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        "CLAUDE_PROJECT_DIR": str(project_dir),
        "HOME": str(Path.home()),
        "PATH": os.environ["PATH"],
    }
    return subprocess.run(
        ["python3", str(_HOOKS / script)],
        input=raw,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=30,
    )


def test_dispatcher_is_the_sole_bash_entry_and_preserves_standalone_denies(
    tmp_path: Path,
) -> None:
    """The installed Bash path is one process and preserves each guard's bytes."""
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"implementation": {"plugin": "livespec-orchestrator-beads-fabro"}}),
        encoding="utf-8",
    )
    declared = json.loads((_HOOKS / "hooks.json").read_text(encoding="utf-8"))
    bash_entries = [
        entry for entry in declared["hooks"]["PreToolUse"] if entry.get("matcher") == "Bash"
    ]
    assert [hook["command"] for entry in bash_entries for hook in entry["hooks"]] == [
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_dispatch.py"'
    ]

    cases = (
        ("livespec_footgun_guard.py", _payload(command="tmux kill-server")),
        ("block_raw_bd_create.py", _payload(command="bd create -t dispatcher")),
        (
            "block_auto_memory.py",
            _payload(command=f"echo x > {Path.home()}/.codex/memories/dispatcher.md"),
        ),
    )
    for script, raw in cases:
        standalone = _run(script=script, raw=raw, project_dir=tmp_path)
        dispatched = _run(script="pretooluse_dispatch.py", raw=raw, project_dir=tmp_path)
        assert standalone.returncode == 0, standalone.stderr
        assert dispatched.returncode == 0, dispatched.stderr
        assert dispatched.stdout == standalone.stdout
