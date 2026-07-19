"""Install-shaped subprocess tests for the plugin-shipped Codex hooks.

The other `tests/hooks/` modules run the hooks from the REPO checkout, where
the repo root happens to be reachable. That is NOT the shape Codex runs them
in. Codex copies ONLY the packaged plugin subtree — `.agents/plugins/marketplace.json`
`plugins[0].source.path` is `./livespec`, so `livespec/` and nothing above it —
into an install cache laid out as `<cache>/livespec/<version>/hooks/<file>.py`,
and invokes each hook with a bare `python3`.

Anything a shipped hook imports from OUTSIDE `livespec/` therefore does not
exist at runtime. When that import sits at module scope it raises before the
hook's `main()` try/except, the process exits non-zero, and the hook fails
OPEN — a dangerous command runs unblocked while the guard looks installed and
wired. This module reproduces the install shape so that failure mode is caught
here instead of in production.

Contract under test:

- Every hook declared in the shipped `hooks/hooks.json` STARTS cleanly under
  the install layout: exit 0, no traceback on stderr, on a benign payload.
- The footgun guard returns the SAME verdicts under the install layout as it
  does in-repo, over a corpus of tmux-fleet-kill hazards and lookalikes.

Every command string in the corpus is inert DATA fed to the guard's stdin. The
guard is a classifier: it reads a payload and prints a verdict. Nothing in this
module ever executes a corpus string.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PLUGIN_SOURCE = _REPO_ROOT / "livespec"
_HOOKS_JSON = _PLUGIN_SOURCE / "hooks" / "hooks.json"
_PLUGIN_MANIFEST = _PLUGIN_SOURCE / ".codex-plugin" / "plugin.json"

# A Stop-event payload naming a transcript that does not exist: every Stop hook
# fails open on it, so a clean start is the only thing being asserted.
_BENIGN_STOP_PAYLOAD = json.dumps(
    {"session_id": "install-shape", "transcript_path": "/nonexistent", "stop_hook_active": False}
)
_BENIGN_PAYLOAD_BY_MATCHER = {
    "Bash": json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status --short"}}),
    "Write": json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/tmp/benign.txt"}}),
    "Edit": json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/tmp/benign.txt"}}),
    "apply_patch": json.dumps({"tool_name": "apply_patch", "tool_input": {"input": ""}}),
}

# (label, command string, expected verdict). DATA ONLY — never executed.
_GUARD_CORPUS = (
    ("bare unscoped kill-server", "tmux kill-server", "deny"),
    ("absolute-path kill-server", "/usr/bin/tmux kill-server", "deny"),
    ("env-prefixed TMUX_TMPDIR", "env TMUX_TMPDIR=/tmp tmux kill-server", "deny"),
    ("leading env assignment", "TMUX_TMPDIR=/tmp tmux kill-server", "deny"),
    ("explicit default label", "tmux -L default kill-server", "deny"),
    ("fleet default socket", "tmux -S /tmp/tmux-1000/default kill-server", "deny"),
    ("shell -c wrapper", "bash -c 'tmux kill-server'", "deny"),
    ("chained after cd", "cd /tmp && tmux kill-server", "deny"),
    ("process killer pkill", "pkill -f tmux", "deny"),
    ("process killer killall", "killall tmux", "deny"),
    ("scoped scratch label", "tmux -L lc_e2e_123 kill-server", "allow"),
    ("scoped scratch socket", "tmux -S /tmp/scratch-abc/sock kill-server", "allow"),
    ("non-destructive tmux", "tmux list-sessions", "allow"),
    ("hazard inside echo data", "echo 'tmux kill-server'", "allow"),
    ("unrelated command", "git status --short", "allow"),
)


def _hook_script_names() -> list[str]:
    """Every hook script name referenced by the shipped hooks.json, in order."""
    declared = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    names: list[str] = []
    for entries in declared.values():
        for entry in entries:
            for hook in entry["hooks"]:
                name = hook["command"].rsplit("/", 1)[-1].rstrip('"')
                if name not in names:
                    names.append(name)
    return names


def _hook_matchers() -> dict[str, str]:
    """Map each hook script name to the event matcher it is declared under."""
    declared = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    matchers: dict[str, str] = {}
    for entries in declared.values():
        for entry in entries:
            for hook in entry["hooks"]:
                name = hook["command"].rsplit("/", 1)[-1].rstrip('"')
                matchers.setdefault(name, entry.get("matcher", ""))
    return matchers


@pytest.fixture(scope="module")
def install_cache_hooks(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The shipped subtree ALONE, laid out as Codex's install cache lays it out.

    Copies `livespec/` — and nothing above it — to
    `<tmp>/livespec/<version>/`, mirroring the real cache path
    `~/.codex/plugins/cache/livespec/<version>/hooks/<file>.py`. `__pycache__`
    is excluded so no stale compiled module can satisfy an import the shipped
    tree cannot satisfy on its own.
    """
    version = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))["version"]
    cache_root = tmp_path_factory.mktemp("codex-install-cache")
    destination = cache_root / "livespec" / version
    shutil.copytree(_PLUGIN_SOURCE, destination, ignore=shutil.ignore_patterns("__pycache__"))
    return destination / "hooks"


def _run_installed_hook(*, hooks_dir: Path, script: str, stdin: str) -> subprocess.CompletedProcess:
    """Run one installed hook as Codex does: bare interpreter, no repo on any path.

    `-E` makes the interpreter ignore PYTHONPATH (and every other PYTHON* env
    var), and the environment passed in carries no repo path at all, so the
    only importable locations are the interpreter's own stdlib and the script's
    own directory inside the install cache.
    """
    return subprocess.run(
        [sys.executable, "-E", str(hooks_dir / script)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(hooks_dir.parent),
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(hooks_dir.parent),
            "LIVESPEC_CODEX_BACKGROUND_MEMORY_DB": str(hooks_dir.parent / "absent.sqlite"),
        },
        check=False,
    )


def _verdict(*, result: subprocess.CompletedProcess) -> str:
    if result.returncode != 0:
        return f"crash(exit={result.returncode}): {result.stderr.strip()[-300:]}"
    if not result.stdout.strip():
        return "allow"
    payload = json.loads(result.stdout)
    return payload["hookSpecificOutput"]["permissionDecision"]


@pytest.mark.parametrize("script", _hook_script_names())
def test_every_shipped_hook_starts_cleanly_under_the_install_layout(
    install_cache_hooks: Path,
    script: str,
) -> None:
    matcher = _hook_matchers()[script]
    stdin = _BENIGN_PAYLOAD_BY_MATCHER.get(matcher, _BENIGN_STOP_PAYLOAD)

    result = _run_installed_hook(hooks_dir=install_cache_hooks, script=script, stdin=stdin)

    assert (
        "Traceback" not in result.stderr
    ), f"{script} raised under the install layout:\n{result.stderr}"
    assert result.returncode == 0, f"{script} exited {result.returncode}:\n{result.stderr}"


@pytest.mark.parametrize(("label", "command", "expected"), _GUARD_CORPUS)
def test_footgun_guard_verdicts_under_the_install_layout(
    install_cache_hooks: Path,
    label: str,
    command: str,
    expected: str,
) -> None:
    stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})

    result = _run_installed_hook(
        hooks_dir=install_cache_hooks,
        script="livespec_footgun_guard.py",
        stdin=stdin,
    )

    assert _verdict(result=result) == expected, f"{label}: wrong verdict under the install layout"
