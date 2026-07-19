"""Evasion corpus for `livespec/hooks/_footgun_tmux.py`.

The footgun guard shipped with a tmux classifier that a leading `env -i`, an
`exec`/`timeout`/`nice` prefix, or an `xargs tmux` target walked straight past.
Each of those was a COMPLETE bypass reaching the host's shared default tmux
socket, which carries live agent sessions.

This module pins the classifier against that whole evasion space in-process,
one case per known bypass family, plus the false-positive direction: a guard
that blocks legitimate scoped work is its own defect, because it pushes agents
into working around it.

Every command string below is INERT DATA handed to a pure classifier function.
`check_tmux_segment` reads a string and returns a verdict; nothing in this
module executes a tmux, pkill, or killall command, and nothing here may be
changed to do so.

The module under test lives in `livespec/hooks/` (added to `sys.path` below,
exactly as `python3 <guard>.py` puts that dir on `sys.path[0]` at runtime).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _footgun_shell import segments  # noqa: E402 — path-dependent import.
from _footgun_tmux import (  # noqa: E402 — path-dependent import.
    TMUX_PARSE_REASON,
    TMUX_REASON,
    check_tmux_segment,
)

__all__: list[str] = []

# Every one of these reaches a shared/default tmux server. DATA, never executed.
_DENY_CASES = (
    # Binary spelling and resolution.
    ("bare unscoped", "tmux kill-server"),
    ("absolute path", "/usr/bin/tmux kill-server"),
    ("relative path", "./tmux kill-server"),
    # Wrapper prefixes that re-exec the real command.
    ("env -i clears TMUX_TMPDIR", "env -i tmux kill-server"),
    ("env -u wrapper", "env -u TMUX_TMPDIR tmux kill-server"),
    ("env with assignment", "env TMUX_TMPDIR=/tmp tmux kill-server"),
    ("leading assignment", "TMUX_TMPDIR=/tmp tmux kill-server"),
    ("command builtin", "command tmux kill-server"),
    ("exec prefix", "exec tmux kill-server"),
    ("sudo prefix", "sudo tmux kill-server"),
    ("sudo with flag", "sudo -u ubuntu tmux kill-server"),
    ("nice prefix", "nice tmux kill-server"),
    ("nice -n argument", "nice -n 5 tmux kill-server"),
    ("nice numeric flag", "nice -5 tmux kill-server"),
    ("timeout duration", "timeout 5 tmux kill-server"),
    ("timeout flags then duration", "timeout -k 10 5s tmux kill-server"),
    ("nohup", "nohup tmux kill-server"),
    ("setsid", "setsid tmux kill-server"),
    ("stdbuf", "stdbuf -oL tmux kill-server"),
    ("ionice", "ionice -c2 -n7 tmux kill-server"),
    ("time", "time tmux kill-server"),
    ("mise exec", "mise exec -- tmux kill-server"),
    ("stacked wrappers", "sudo env -i timeout 5 tmux kill-server"),
    ("wrapper double dash", "env -- tmux kill-server"),
    # Scope spellings that still resolve to the fleet server.
    ("explicit default label", "tmux -L default kill-server"),
    ("clustered default label", "tmux -Ldefault kill-server"),
    ("equals default label", "tmux -L=default kill-server"),
    ("label after subcommand", "tmux kill-server -L default"),
    ("fleet default socket", "tmux -S /tmp/tmux-1000/default kill-server"),
    ("double slash socket", "tmux -S /tmp/tmux-1000//default kill-server"),
    ("dotdot socket", "tmux -S /tmp/tmux-1000/../tmux-1000/default kill-server"),
    ("dotdot into namespace", "tmux -S /tmp/scratch/../tmux-1000/default kill-server"),
    ("trailing slash socket", "tmux -S /tmp/tmux-1000/default/ kill-server"),
    ("namespace sibling socket", "tmux -S /tmp/tmux-1000/other kill-server"),
    ("clustered default socket", "tmux -S/tmp/tmux-1000/default kill-server"),
    ("fleet-named socket", "tmux -S /tmp/fleet-sock kill-server"),
    ("empty socket value", "tmux kill-server -S"),
    ("empty label value", "tmux kill-server -L"),
    # Nested payloads.
    ("bash -c", "bash -c 'tmux kill-server'"),
    ("sh -lc login shell", "sh -lc 'tmux kill-server'"),
    ("zsh -c", "zsh -c 'tmux kill-server'"),
    ("zsh -ic interactive", "zsh -ic 'tmux kill-server'"),
    ("clustered -c payload", "sh -c'tmux kill-server'"),
    ("doubly nested", "bash -c \"bash -c 'tmux kill-server'\""),
    ("xargs indirect", "echo kill-server | xargs tmux"),
    ("xargs with flags", "echo x | xargs -n 1 tmux"),
    ("xargs double dash", "echo x | xargs -- tmux"),
    ("xargs into shell", "echo x | xargs sh -c 'tmux kill-server'"),
    ("command substitution", "$(echo tmux) kill-server"),
    # Separators and control operators.
    ("chained after cd", "cd /tmp && tmux kill-server"),
    ("semicolon chain", "echo hi; tmux kill-server"),
    ("pipe chain", "true | tmux kill-server"),
    ("or chain", "false || tmux kill-server"),
    ("newline chain", "echo hi\ntmux kill-server"),
    ("background operator", "tmux kill-server &"),
    # Process killers.
    ("pkill exact", "pkill tmux"),
    ("pkill -f", "pkill -f tmux"),
    ("pkill full match", "pkill -f 'tmux -L default'"),
    ("pkill server binary", "pkill -f /usr/bin/tmux"),
    ("killall", "killall tmux"),
    ("killall with signal", "killall -9 tmux"),
    # Parse-hostile but hazard-shaped: fail CLOSED.
    ("unbalanced quote hazard", "tmux kill-server '"),
)

# Legitimate work the guard must NOT block. A false positive here pushes agents
# into working around the guard, which is how the fleet gets killed anyway.
_ALLOW_CASES = (
    ("scoped label", "tmux -L lc_e2e_1 kill-server"),
    ("scoped label numeric suffix", "tmux -L lc_e2e_123 kill-server"),
    ("scoped socket", "tmux -S /tmp/scratch-x/sock kill-server"),
    ("scoped socket abc", "tmux -S /tmp/scratch-abc/sock kill-server"),
    ("scoped label after subcommand", "tmux kill-server -L scratch99"),
    ("scoped under env -i", "env -i tmux -L scratch9 kill-server"),
    ("scoped under exec", "exec tmux -L scratch9 kill-server"),
    ("scoped xargs target", "echo kill-server | xargs tmux -L scratch9"),
    ("list sessions", "tmux list-sessions"),
    ("new scoped session", "tmux -L scratch new -d -s probe"),
    ("scoped kill-session", "tmux -L scratch9 kill-session -t x"),
    ("quoted mention", "echo 'tmux kill-server'"),
    ("grep pattern", "git log --grep='tmux kill-server'"),
    ("commit message", "git commit -m 'never run tmux kill-server'"),
    ("heredoc body", "cat <<'EOF'\ntmux kill-server\nEOF"),
    ("python string", "python3 -c \"print('tmux kill-server')\""),
    ("pkill unrelated process", "pkill -f my-worker"),
    ("unrelated command", "ls -la"),
    ("plain git", "git status --short"),
    ("unbalanced quote benign", "echo 'unterminated"),
    # Wrappers whose arguments run to the end of the token stream: peeling must
    # terminate on exhaustion rather than reading past it.
    ("wrapper with no command", "env -i"),
    ("xargs with no target", "echo x | xargs -n 1"),
    ("mise with no command", "mise exec --"),
)


def _blocked(*, command: str) -> bool:
    """Compose the classifier exactly as the guard's main loop composes it."""
    return any(check_tmux_segment(seg=seg)[0] for seg in segments(command=command))


@pytest.mark.parametrize(("label", "command"), _DENY_CASES)
def test_classifier_denies_every_known_evasion(label: str, command: str) -> None:
    assert _blocked(command=command) is True, f"{label}: evasion not blocked"


@pytest.mark.parametrize(("label", "command"), _ALLOW_CASES)
def test_classifier_allows_scoped_and_benign_commands(label: str, command: str) -> None:
    assert _blocked(command=command) is False, f"{label}: legitimate command blocked"


def test_deny_reasons_name_the_scoped_alternative() -> None:
    _, reason = check_tmux_segment(seg="tmux kill-server")
    assert reason == TMUX_REASON
    assert "-L <agent-scope>" in reason

    _, parse_reason = check_tmux_segment(seg="tmux kill-server '")
    assert parse_reason == TMUX_PARSE_REASON
    assert "fail CLOSED" in parse_reason


def test_empty_segment_is_not_a_hazard() -> None:
    blocked, reason = check_tmux_segment(seg="")
    assert blocked is False
    assert reason == ""


def test_depth_budget_is_exhausted_explicitly() -> None:
    blocked, _ = check_tmux_segment(seg="tmux kill-server", depth=99)
    assert blocked is False
