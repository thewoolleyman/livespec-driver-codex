"""Unit tests for `livespec/hooks/_footgun_shell.py`.

These cover the shell-tokenization primitives extracted from the footgun guard
(livespec epic livespec-i5ebqd, file_lloc decomposition) DIRECTLY — the guard's
own subprocess suite in test_livespec_footgun_guard.py exercises them
end-to-end, but the decomposition moves this logic behind a public module API,
so it earns its own direct coverage.

The module lives under `livespec/hooks/` (added to `sys.path` below, exactly as
`python3 <guard>.py` puts that dir on `sys.path[0]` at runtime).
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import _footgun_shell  # noqa: E402 — path-dependent import after sys.path insert.

__all__: list[str] = []


# --------------------------------------------------------------------------
# git_subcommand
# --------------------------------------------------------------------------


def test_git_subcommand_plain_commit() -> None:
    sub, args = _footgun_shell.git_subcommand(tokens=["git", "commit", "-m", "wip"])
    assert sub == "commit"
    assert args == ["-m", "wip"]


def test_git_subcommand_skips_global_opt_with_arg() -> None:
    # `-C <path>` is a global option that consumes its argument; the subcommand
    # is what follows it.
    sub, args = _footgun_shell.git_subcommand(tokens=["git", "-C", "/repo", "push", "origin"])
    assert sub == "push"
    assert args == ["origin"]


def test_git_subcommand_resolves_basename() -> None:
    sub, _ = _footgun_shell.git_subcommand(tokens=["/usr/bin/git", "status"])
    assert sub == "status"


def test_git_subcommand_non_git_is_none() -> None:
    sub, args = _footgun_shell.git_subcommand(tokens=["echo", "hi"])
    assert sub is None
    assert args == []


def test_git_subcommand_bare_git_is_none() -> None:
    sub, args = _footgun_shell.git_subcommand(tokens=["git"])
    assert sub is None
    assert args == []


# --------------------------------------------------------------------------
# strip_leading_noise
# --------------------------------------------------------------------------


def test_strip_leading_noise_mise_exec_wrapper() -> None:
    core, lefthook_off = _footgun_shell.strip_leading_noise(
        tokens=["mise", "exec", "--", "git", "commit"]
    )
    assert core == ["git", "commit"]
    assert lefthook_off is False


def test_strip_leading_noise_flags_lefthook_disable() -> None:
    core, lefthook_off = _footgun_shell.strip_leading_noise(tokens=["LEFTHOOK=0", "git", "commit"])
    assert core == ["git", "commit"]
    assert lefthook_off is True


def test_strip_leading_noise_generic_env_and_sudo() -> None:
    core, lefthook_off = _footgun_shell.strip_leading_noise(
        tokens=["FOO=bar", "sudo", "git", "status"]
    )
    assert core == ["git", "status"]
    assert lefthook_off is False


def test_strip_leading_noise_leaves_plain_command() -> None:
    core, lefthook_off = _footgun_shell.strip_leading_noise(tokens=["git", "commit"])
    assert core == ["git", "commit"]
    assert lefthook_off is False


# Every wrapper below re-execs the command that follows it, so treating the
# wrapper name as the invocation is a bypass of every downstream check. Each
# entry is (label, tokens, expected remaining core).
_WRAPPER_CASES = [
    ("exec", ["exec", "git", "commit"], ["git", "commit"]),
    ("command builtin", ["command", "git", "commit"], ["git", "commit"]),
    ("nice bare", ["nice", "git", "commit"], ["git", "commit"]),
    ("nice -n argument", ["nice", "-n", "5", "git", "commit"], ["git", "commit"]),
    ("nice numeric flag", ["nice", "-5", "git", "commit"], ["git", "commit"]),
    ("timeout duration", ["timeout", "5", "git", "commit"], ["git", "commit"]),
    ("timeout flag then duration", ["timeout", "-k", "10", "5s", "git"], ["git"]),
    ("env -i", ["env", "-i", "git", "commit"], ["git", "commit"]),
    ("env -u NAME", ["env", "-u", "HOME", "git", "commit"], ["git", "commit"]),
    ("env double dash", ["env", "--", "git", "commit"], ["git", "commit"]),
    ("nohup", ["nohup", "git", "commit"], ["git", "commit"]),
    ("setsid", ["setsid", "git", "commit"], ["git", "commit"]),
    ("stdbuf", ["stdbuf", "-oL", "git", "commit"], ["git", "commit"]),
    ("ionice", ["ionice", "-c2", "-n7", "git", "commit"], ["git", "commit"]),
    ("time", ["time", "git", "commit"], ["git", "commit"]),
    ("sudo with flag", ["sudo", "-u", "ubuntu", "git", "commit"], ["git", "commit"]),
    ("absolute wrapper path", ["/usr/bin/env", "-i", "git"], ["git"]),
    ("stacked wrappers", ["sudo", "env", "-i", "timeout", "5", "git"], ["git"]),
    ("wrapper then assignment", ["sudo", "FOO=bar", "git"], ["git"]),
    ("wrapper alone", ["env"], []),
]


@pytest.mark.parametrize(("label", "tokens", "expected"), _WRAPPER_CASES)
def test_strip_leading_noise_peels_every_reexec_wrapper(
    label: str, tokens: list[str], expected: list[str]
) -> None:
    core, lefthook_off = _footgun_shell.strip_leading_noise(tokens=tokens)
    assert core == expected, label
    assert lefthook_off is False


def test_strip_leading_noise_sees_lefthook_disable_behind_a_wrapper() -> None:
    # The assignment sits AFTER a wrapper, so a stripper that only inspected the
    # leading position would miss it.
    core, lefthook_off = _footgun_shell.strip_leading_noise(
        tokens=["sudo", "env", "LEFTHOOK=0", "git", "commit"]
    )
    assert core == ["git", "commit"]
    assert lefthook_off is True


def test_strip_leading_noise_flags_lefthook_disable_before_a_wrapper() -> None:
    core, lefthook_off = _footgun_shell.strip_leading_noise(
        tokens=["LEFTHOOK=false", "sudo", "git", "commit"]
    )
    assert core == ["git", "commit"]
    assert lefthook_off is True


# --------------------------------------------------------------------------
# segments (incl. here-doc body stripping)
# --------------------------------------------------------------------------


def test_segments_splits_operators() -> None:
    assert _footgun_shell.segments(command="a && b ; c | d") == ["a", "b", "c", "d"]


def test_segments_drops_heredoc_body() -> None:
    # The `--no-verify` string lives ONLY in the here-doc BODY (file data), so
    # it must not surface as an inspectable segment.
    segs = _footgun_shell.segments(command="cat <<'EOF'\ngit commit --no-verify\nEOF")
    assert all("--no-verify" not in s for s in segs)
    assert segs == ["cat <<'EOF'"]


def test_segments_roundtrips_through_shlex_for_git() -> None:
    # A realistic multi-segment command: only the second segment is a git call.
    segs = _footgun_shell.segments(command="echo ok && git commit --no-verify")
    assert segs == ["echo ok", "git commit --no-verify"]
    sub, args = _footgun_shell.git_subcommand(tokens=shlex.split(segs[1]))
    assert sub == "commit"
    assert "--no-verify" in args
