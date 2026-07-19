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

import shlex
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
    # --- Reviewer corpus: wrapper / prefix evasions -------------------------
    ("W1 timeout wrapper", "timeout 5 tmux kill-server"),
    ("W2 nohup wrapper", "nohup tmux kill-server"),
    ("W3 exec builtin", "exec tmux kill-server"),
    ("W4 command builtin", "command tmux kill-server"),
    ("W5 nice wrapper", "nice -n 5 tmux kill-server"),
    ("W6 sudo prefix", "sudo tmux kill-server"),
    ("W7 mise exec --", "mise exec -- tmux kill-server"),
    ("W8 xargs", "echo | xargs tmux kill-server"),
    ("W9 stdbuf", "stdbuf -o0 tmux kill-server"),
    # --- Reviewer corpus: scope-flag ordering and spelling ------------------
    ("S1 -L default after subcommand", "tmux kill-server -L default"),
    ("S2 -Ldefault attached", "tmux -Ldefault kill-server"),
    ("S3 -L=default", "tmux -L=default kill-server"),
    ("S4 -S bare relative name", "tmux -S default kill-server"),
    ("S5 double slash", "tmux -S /tmp/tmux-1000//default kill-server"),
    ("S6 dotdot spelling", "tmux -S /tmp/tmux-1000/../tmux-1000/default kill-server"),
    ("S7 dot spelling", "tmux -S /tmp/./tmux-1000/./default kill-server"),
    ("S8 trailing slash", "tmux -S /tmp/tmux-1000/default/ kill-server"),
    ("S9 -L scratch then -S default", "tmux -L scratch -S /tmp/tmux-1000/default kill-server"),
    ("S10 -S default then -L scratch", "tmux -S /tmp/tmux-1000/default -L scratch kill-server"),
    ("S11 agents tmpdir default", "tmux -S /tmp/tmux-agents-1000/default kill-server"),
    ("S12 -S attached default", "tmux -S/tmp/tmux-1000/default kill-server"),
    ("S13 repeated -S, last wins", "tmux -S /tmp/scratch/a -S /tmp/tmux-1000/default kill-server"),
    ("S14 repeated -L, last wins", "tmux -L scratch -L default kill-server"),
    ("S15 namespace sibling socket", "tmux -S /tmp/tmux-1000/other kill-server"),
    ("S16 empty socket value", "tmux kill-server -S"),
    ("S17 empty label value", "tmux kill-server -L"),
    # --- Reviewer corpus: nesting depth -------------------------------------
    ("N1 2-level -c", "bash -c 'bash -c \"tmux kill-server\"'"),
    (
        "N2 5-level -c exhausts the budget",
        'bash -c "bash -c \'bash -c \\"bash -c \\\\\\"bash -c tmux kill-server' '\\\\\\"\\"\'"',
    ),
    ("N3 sh -lc", "sh -lc 'tmux kill-server'"),
    ("N4 attached -ctmux", "bash -ctmux' kill-server'"),
    ("N5 zsh -c", "zsh -c 'tmux kill-server'"),
    ("N6 zsh -ic interactive", "zsh -ic 'tmux kill-server'"),
    ("N7 nested payload with its own separator", "sh -c 'cd /tmp && tmux kill-server'"),
    ("N8 eval payload", "eval 'tmux kill-server'"),
    ("N9 xargs into shell", "echo x | xargs sh -c 'tmux kill-server'"),
    ("N10 xargs with flags", "echo x | xargs -n 1 tmux"),
    ("N11 xargs double dash", "echo x | xargs -- tmux"),
    # --- Reviewer corpus: process killers -----------------------------------
    ("P1 pkill anchored regex", "pkill -f '^tmux'"),
    ("P2 pkill attached -ftmux", "pkill -ftmux"),
    ("P3 pkill exact", "pkill -x tmux"),
    ("P4 killall -9", "killall -9 tmux"),
    ("P5 pkill server pattern", "pkill -f 'tmux: server'"),
    ("P6 pkill bare", "pkill tmux"),
    ("P7 pkill server binary path", "pkill -f /usr/bin/tmux"),
    ("P8 killall bare", "killall tmux"),
    ("P9 kill via pgrep substitution", "kill -9 $(pgrep tmux)"),
    # --- Reviewer corpus: separators, grouping, substitution ----------------
    ("C1 newline separator", "cd /tmp\ntmux kill-server"),
    ("C2 background operator", "tmux kill-server &"),
    ("C3 subshell parens", "(tmux kill-server)"),
    ("C4 command substitution", "$(echo tmux) kill-server"),
    ("C5 brace group", "{ tmux kill-server; }"),
    ("C6 absolute path", "/usr/bin/tmux kill-server"),
    ("C7 relative path", "./tmux kill-server"),
    ("C8 semicolon chain", "echo hi; tmux kill-server"),
    ("C9 pipe chain", "true | tmux kill-server"),
    ("C10 or chain", "false || tmux kill-server"),
    ("C11 backslash line continuation", "tmux \\\n kill-server"),
    ("C12 subshell behind a wrapper", "nohup (tmux kill-server)"),
    # --- Reviewer corpus: environment-clearing wrappers ---------------------
    ("E1 env -i clears TMUX_TMPDIR", "env -i tmux kill-server"),
    ("E2 env -u wrapper", "env -u TMUX_TMPDIR tmux kill-server"),
    ("E3 env with assignment", "env TMUX_TMPDIR=/tmp tmux kill-server"),
    ("E4 leading assignment", "TMUX_TMPDIR=/tmp tmux kill-server"),
    ("E5 sudo with flag", "sudo -u ubuntu tmux kill-server"),
    ("E6 stacked wrappers", "sudo env -i timeout 5 tmux kill-server"),
    ("E7 setsid", "setsid tmux kill-server"),
    ("E8 ionice", "ionice -c2 -n7 tmux kill-server"),
    ("E9 time", "time tmux kill-server"),
    ("E10 chained after cd", "cd /tmp && tmux kill-server"),
    # --- Parse-hostile but hazard-shaped: must fail CLOSED ------------------
    ("X1 unbalanced quote hazard", "tmux kill-server '"),
)

# Legitimate work the guard must NOT block. A false positive here pushes agents
# into working around the guard, which is how the fleet gets killed anyway.
_ALLOW_CASES = (
    # --- Reviewer corpus: the false-positive direction ----------------------
    ("F1 scoped -L scratch", "tmux -L lc_e2e_9 kill-server"),
    ("F2 scoped -L attached", "tmux -Lscratch kill-server"),
    ("F3 scoped -S scratch", "tmux -S /tmp/scratch-abc/sock kill-server"),
    ("F4 echo with a quoted semicolon", "echo 'first; tmux kill-server'"),
    ("F5 grep pattern", "grep -r 'tmux kill-server' /data/projects"),
    ("F6 git commit message", "git commit -m 'guard blocks tmux kill-server'"),
    ("F7 heredoc body", "cat > /tmp/x <<'EOF'\ntmux kill-server\nEOF"),
    ("F8 tmux list-sessions", "tmux list-sessions"),
    ("F9 python string", "python3 -c \"print('tmux kill-server')\""),
    ("F10 pkill non-tmux", "pkill -f myserver"),
    ("F11 scoped kill-session", "tmux -L scratch kill-session -t foo"),
    ("F12 echo pkill mention", "echo 'do not run pkill -f tmux'"),
    ("F13 fleet-NAMED scratch socket", "tmux -S /tmp/scratch/fleetwood kill-server"),
    ("F14 fleet-named socket in /tmp", "tmux -S /tmp/fleet-sock kill-server"),
    ("F15 -S wins over a default -L", "tmux -L default -S /tmp/scratch/sock kill-server"),
    ("F16 git log grep", "git log --grep='tmux kill-server'"),
    ("F17 scoped under env -i", "env -i tmux -L scratch9 kill-server"),
    ("F18 scoped under exec", "exec tmux -L scratch9 kill-server"),
    ("F19 scoped xargs target", "echo kill-server | xargs tmux -L scratch9"),
    ("F20 new scoped session", "tmux -L scratch new -d -s probe"),
    ("F21 kill with a plain pid", "kill -9 12345"),
    ("F22 eval of benign text", "eval 'echo hi'"),
    ("F23 pgrep alone is read-only", "pgrep tmux"),
    ("F24 unrelated command", "ls -la"),
    ("F25 plain git", "git status --short"),
    ("F26 empty command", ""),
    # --- Wrappers and lexing edges that must terminate cleanly --------------
    ("F27 xargs flags run to end of tokens", "echo x | xargs -n 1"),
    ("F28 eval with no payload", "eval"),
    ("F29 unbalanced quote, no hazard", "echo 'unterminated"),
    ("F30 mise with no command", "mise exec --"),
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


def test_deep_nesting_terminates_and_denies() -> None:
    """Nesting past the depth budget must fail CLOSED, not open.

    An earlier guard returned "allowed" once the budget ran out, so simply
    nesting `sh -c` six deep walked the whole classifier. Nothing legitimate
    nests that deep, so running out of budget is evidence of evasion.
    """
    payload = "tmux kill-server"
    for _ in range(8):
        payload = f"sh -c {shlex.quote(payload)}"
    blocked, _ = check_tmux_segment(seg=payload)
    assert blocked is True


def test_depth_budget_exhaustion_denies() -> None:
    blocked, reason = check_tmux_segment(seg="anything at all", depth=99)
    assert blocked is True
    assert reason == TMUX_PARSE_REASON
