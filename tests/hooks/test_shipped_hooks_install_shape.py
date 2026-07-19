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
    ("W1 timeout wrapper", "timeout 5 tmux kill-server", "deny"),
    ("W2 nohup wrapper", "nohup tmux kill-server", "deny"),
    ("W3 exec builtin", "exec tmux kill-server", "deny"),
    ("W4 command builtin", "command tmux kill-server", "deny"),
    ("W5 nice wrapper", "nice -n 5 tmux kill-server", "deny"),
    ("W6 sudo prefix", "sudo tmux kill-server", "deny"),
    ("W7 mise exec --", "mise exec -- tmux kill-server", "deny"),
    ("W8 xargs", "echo | xargs tmux kill-server", "deny"),
    ("W9 stdbuf", "stdbuf -o0 tmux kill-server", "deny"),
    ("S1 -L default after subcommand", "tmux kill-server -L default", "deny"),
    ("S2 -Ldefault attached", "tmux -Ldefault kill-server", "deny"),
    ("S3 -L=default", "tmux -L=default kill-server", "deny"),
    ("S4 -S bare relative name", "tmux -S default kill-server", "deny"),
    ("S5 double slash", "tmux -S /tmp/tmux-1000//default kill-server", "deny"),
    ("S6 dotdot spelling", "tmux -S /tmp/tmux-1000/../tmux-1000/default kill-server", "deny"),
    ("S7 dot spelling", "tmux -S /tmp/./tmux-1000/./default kill-server", "deny"),
    ("S8 trailing slash", "tmux -S /tmp/tmux-1000/default/ kill-server", "deny"),
    (
        "S9 -L scratch then -S default",
        "tmux -L scratch -S /tmp/tmux-1000/default kill-server",
        "deny",
    ),
    (
        "S10 -S default then -L scratch",
        "tmux -S /tmp/tmux-1000/default -L scratch kill-server",
        "deny",
    ),
    ("S11 agents tmpdir default", "tmux -S /tmp/tmux-agents-1000/default kill-server", "deny"),
    ("S12 -S attached default", "tmux -S/tmp/tmux-1000/default kill-server", "deny"),
    (
        "S13 repeated -S, last wins",
        "tmux -S /tmp/scratch/a -S /tmp/tmux-1000/default kill-server",
        "deny",
    ),
    ("S14 repeated -L, last wins", "tmux -L scratch -L default kill-server", "deny"),
    ("S15 namespace sibling socket", "tmux -S /tmp/tmux-1000/other kill-server", "deny"),
    ("S16 empty socket value", "tmux kill-server -S", "deny"),
    ("S17 empty label value", "tmux kill-server -L", "deny"),
    ("N1 2-level -c", "bash -c 'bash -c \"tmux kill-server\"'", "deny"),
    (
        "N2 5-level -c exhausts the budget",
        'bash -c "bash -c \'bash -c \\"bash -c \\\\\\"bash -c tmux kill-server\\\\\\"\\"\'"',
        "deny",
    ),
    ("N3 sh -lc", "sh -lc 'tmux kill-server'", "deny"),
    ("N4 attached -ctmux", "bash -ctmux' kill-server'", "deny"),
    ("N5 zsh -c", "zsh -c 'tmux kill-server'", "deny"),
    ("N6 zsh -ic interactive", "zsh -ic 'tmux kill-server'", "deny"),
    ("N7 nested payload with its own separator", "sh -c 'cd /tmp && tmux kill-server'", "deny"),
    ("N8 eval payload", "eval 'tmux kill-server'", "deny"),
    ("N9 xargs into shell", "echo x | xargs sh -c 'tmux kill-server'", "deny"),
    ("N10 xargs with flags", "echo x | xargs -n 1 tmux", "deny"),
    ("N11 xargs double dash", "echo x | xargs -- tmux", "deny"),
    ("P1 pkill anchored regex", "pkill -f '^tmux'", "deny"),
    ("P2 pkill attached -ftmux", "pkill -ftmux", "deny"),
    ("P3 pkill exact", "pkill -x tmux", "deny"),
    ("P4 killall -9", "killall -9 tmux", "deny"),
    ("P5 pkill server pattern", "pkill -f 'tmux: server'", "deny"),
    ("P6 pkill bare", "pkill tmux", "deny"),
    ("P7 pkill server binary path", "pkill -f /usr/bin/tmux", "deny"),
    ("P8 killall bare", "killall tmux", "deny"),
    ("P9 kill via pgrep substitution", "kill -9 $(pgrep tmux)", "deny"),
    ("C1 newline separator", "cd /tmp\ntmux kill-server", "deny"),
    ("C2 background operator", "tmux kill-server &", "deny"),
    ("C3 subshell parens", "(tmux kill-server)", "deny"),
    ("C4 command substitution", "$(echo tmux) kill-server", "deny"),
    ("C5 brace group", "{ tmux kill-server; }", "deny"),
    ("C6 absolute path", "/usr/bin/tmux kill-server", "deny"),
    ("C7 relative path", "./tmux kill-server", "deny"),
    ("C8 semicolon chain", "echo hi; tmux kill-server", "deny"),
    ("C9 pipe chain", "true | tmux kill-server", "deny"),
    ("C10 or chain", "false || tmux kill-server", "deny"),
    ("C11 backslash line continuation", "tmux \\\n kill-server", "deny"),
    ("C12 subshell behind a wrapper", "nohup (tmux kill-server)", "deny"),
    ("E1 env -i clears TMUX_TMPDIR", "env -i tmux kill-server", "deny"),
    ("E2 env -u wrapper", "env -u TMUX_TMPDIR tmux kill-server", "deny"),
    ("E3 env with assignment", "env TMUX_TMPDIR=/tmp tmux kill-server", "deny"),
    ("E4 leading assignment", "TMUX_TMPDIR=/tmp tmux kill-server", "deny"),
    ("E5 sudo with flag", "sudo -u ubuntu tmux kill-server", "deny"),
    ("E6 stacked wrappers", "sudo env -i timeout 5 tmux kill-server", "deny"),
    ("E7 setsid", "setsid tmux kill-server", "deny"),
    ("E8 ionice", "ionice -c2 -n7 tmux kill-server", "deny"),
    ("E9 time", "time tmux kill-server", "deny"),
    ("E10 chained after cd", "cd /tmp && tmux kill-server", "deny"),
    ("X1 unbalanced quote hazard", "tmux kill-server '", "deny"),
    ("F1 scoped -L scratch", "tmux -L lc_e2e_9 kill-server", "allow"),
    ("F2 scoped -L attached", "tmux -Lscratch kill-server", "allow"),
    ("F3 scoped -S scratch", "tmux -S /tmp/scratch-abc/sock kill-server", "allow"),
    ("F4 echo with a quoted semicolon", "echo 'first; tmux kill-server'", "allow"),
    ("F5 grep pattern", "grep -r 'tmux kill-server' /data/projects", "allow"),
    ("F6 git commit message", "git commit -m 'guard blocks tmux kill-server'", "allow"),
    ("F7 heredoc body", "cat > /tmp/x <<'EOF'\ntmux kill-server\nEOF", "allow"),
    ("F8 tmux list-sessions", "tmux list-sessions", "allow"),
    ("F9 python string", "python3 -c \"print('tmux kill-server')\"", "allow"),
    ("F10 pkill non-tmux", "pkill -f myserver", "allow"),
    ("F11 scoped kill-session", "tmux -L scratch kill-session -t foo", "allow"),
    ("F12 echo pkill mention", "echo 'do not run pkill -f tmux'", "allow"),
    ("F13 fleet-NAMED scratch socket", "tmux -S /tmp/scratch/fleetwood kill-server", "allow"),
    ("F14 fleet-named socket in /tmp", "tmux -S /tmp/fleet-sock kill-server", "allow"),
    ("F15 -S wins over a default -L", "tmux -L default -S /tmp/scratch/sock kill-server", "allow"),
    ("F16 git log grep", "git log --grep='tmux kill-server'", "allow"),
    ("F17 scoped under env -i", "env -i tmux -L scratch9 kill-server", "allow"),
    ("F18 scoped under exec", "exec tmux -L scratch9 kill-server", "allow"),
    ("F19 scoped xargs target", "echo kill-server | xargs tmux -L scratch9", "allow"),
    ("F20 new scoped session", "tmux -L scratch new -d -s probe", "allow"),
    ("F21 kill with a plain pid", "kill -9 12345", "allow"),
    ("F22 eval of benign text", "eval 'echo hi'", "allow"),
    ("F23 pgrep alone is read-only", "pgrep tmux", "allow"),
    ("F24 unrelated command", "ls -la", "allow"),
    ("F25 plain git", "git status --short", "allow"),
    ("F27 xargs flags run to end of tokens", "echo x | xargs -n 1", "allow"),
    ("F28 eval with no payload", "eval", "allow"),
    ("F29 unbalanced quote, no hazard", "echo 'unterminated", "allow"),
    ("F30 mise with no command", "mise exec --", "allow"),
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
