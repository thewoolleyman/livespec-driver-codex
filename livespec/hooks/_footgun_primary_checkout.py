#!/usr/bin/env python3
"""
Primary-checkout-edit detection for the livespec footgun guard.

Extracted from `livespec_footgun_guard.py` (livespec epic livespec-i5ebqd,
file_lloc decomposition) as the cohesive "would this shell segment WRITE files
at a livespec PRIMARY checkout?" sub-responsibility: extracting the candidate
write-target paths from a segment (redirections / `tee` / `sed -i` / `dd of=` /
`git apply|am`) and deciding whether a path resolves into a repo that is its own
primary checkout (`git config --get livespec.primaryPath` == its worktree root).

Imports the git-invocation primitive from `_footgun_shell` (the leaf module);
the main guard imports the public surface here. This module never imports the
main guard, so the guard's import DAG stays acyclic
(shell <- primary_checkout <- guard). Behavior is IDENTICAL to the
pre-extraction inline helpers — a pure cohesion move, not a logic change.

Best-effort throughout: fails CLOSED to "not a primary" / returns [] on any
uncertainty, so the guard fails OPEN (never blocks legitimate work on a guard
bug — the commit-refuse hook + branch protection are the real backstops).
"""

import os
import re
import subprocess
from pathlib import Path

from _footgun_shell import git_subcommand
from _result import Failure, Result, Success

__all__: list[str] = [
    "PRIMARY_EDIT_REASON",
    "is_allowed_primary_runtime_state",
    "is_primary_checkout",
    "redirect_targets",
]

PRIMARY_EDIT_REASON = (
    "NEVER edit files directly at a livespec PRIMARY checkout (a repo whose "
    "`git config --get livespec.primaryPath` equals its own worktree root). "
    "Direct commits / writes at the primary are refused by the family "
    "commit-refuse hook. Do edits in a SECONDARY worktree via `git -C <repo> "
    "worktree add ~/.worktrees/<repo>/<branch> -b <branch> origin/master`, "
    "then PR → merge → cleanup. "
    "(memory feedback_dispatch_no_checkout_master_in_worktree)"
)

_FD_DUP_TARGET = re.compile(r"^(?:[0-9]+|-)$")
_FD_DUP_REDIR = re.compile(r"^[0-9]*[<>]&(?:[0-9]+|-)$")

# Best-effort per-realpath cache: a primary-checkout verdict never changes
# within a single hook invocation, so probe each repo root at most once.
_PRIMARY_CHECKOUT_CACHE: dict[str, bool] = {}


def _primary_worktree_root(*, path: str) -> Result[str | None, Exception]:
    """The declared primary root containing ``path``, if any.

    ⛔ `Success(None)` and `Failure` MUST stay distinct here, and used not to be.
    `None` is a definitive NEGATIVE — this is not a repo, or it is a repo that
    declares no primary, or it declares a different one. A probe error is not
    that; it is "I could not find out". Both used to return `None`, and the two
    callers below need OPPOSITE things from an unknown, so a single `None` could
    not serve them: `is_allowed_primary_runtime_state` must DENY its exception on
    uncertainty (keeping a refusal in force), while `_is_primary_checkout_result`
    must not let uncertainty become the cached answer `False` that DISARMS that
    same refusal.
    """
    real = os.path.realpath(path)
    probe_path = Path(real)
    while not probe_path.is_dir() and probe_path != probe_path.parent:
        probe_path = probe_path.parent
    probe = str(probe_path)
    try:
        toplevel = subprocess.run(
            ["git", "-C", probe, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if toplevel.returncode != 0:
            return Success(None)
        worktree_root = os.path.realpath(toplevel.stdout.strip())
        primary = subprocess.run(
            ["git", "-C", probe, "config", "--get", "livespec.primaryPath"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if primary.returncode != 0:
            return Success(None)
        declared = os.path.realpath(primary.stdout.strip())
        return Success(worktree_root if declared and declared == worktree_root else None)
    except (OSError, subprocess.SubprocessError) as exc:
        return Failure(exc)


def _is_primary_checkout_result(*, path: str) -> Result[bool, Exception]:
    """True iff `path` resolves into a git repo that is its OWN primary checkout.

    A primary checkout is a repo whose `git config --get livespec.primaryPath`
    equals its own worktree root. A missing git, a non-repo path, a config
    without the key, or any subprocess error is a probe FAILURE and rides the
    failure track; deciding what to do about it belongs to the boundary, and
    `is_primary_checkout` is the boundary that fails OPEN to False so a hook can
    never wedge the agent.

    ⛔ ONLY DEFINITIVE ANSWERS ARE CACHED. The `except` arm used to write
    `False` into the cache before returning `Failure`, so the next call for the
    same path returned `Success(False)` — a transient failure laundered into a
    definitive negative, and cached, so it was never retried. The consumer is
    the guard that refuses direct edits at a primary checkout, so one failed git
    probe disarmed that guard for the life of the process and kept it disarmed
    after git recovered.
    """
    try:
        real = os.path.realpath(path)
        if real in _PRIMARY_CHECKOUT_CACHE:
            return Success(_PRIMARY_CHECKOUT_CACHE[real])
        probed = _primary_worktree_root(path=real)
        if isinstance(probed, Failure):
            # NOT cached: an unknown must be retried, never remembered as False.
            return probed
        result = probed.unwrap() is not None
    # os.path.realpath can raise OSError; subprocess.run can raise OSError
    # for git launch failures and SubprocessError for timeouts.
    except (OSError, subprocess.SubprocessError) as exc:
        return Failure(exc)
    _PRIMARY_CHECKOUT_CACHE[real] = result
    return Success(result)


def is_primary_checkout(*, path: str) -> bool:
    result = _is_primary_checkout_result(path=path)
    if isinstance(result, Failure):
        _ = result.failure()
        return False
    return result.unwrap()


def is_allowed_primary_runtime_state(*, path: str) -> bool:
    """Return whether ``path`` is ignored runtime state for its primary repo.

    The exception is deliberately narrow: a target must resolve below exactly
    ``tmp/overseer/<topic>/`` and Git's ignore rules must match the target.
    Any probe uncertainty denies the exception, leaving the caller's primary
    checkout refusal in force.
    """
    probed = _primary_worktree_root(path=path)
    if isinstance(probed, Failure):
        _ = probed.failure()
        return False
    root = probed.unwrap()
    if root is None:
        return False
    target = os.path.realpath(path)
    try:
        relative = os.path.relpath(target, root)
    except ValueError:
        return False
    parts = Path(relative).parts
    if len(parts) < 4 or parts[:2] != ("tmp", "overseer") or not parts[2]:
        return False
    ignored = subprocess.run(
        ["git", "-C", root, "check-ignore", "--quiet", "--no-index", "--", relative],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return ignored.returncode == 0


def _redirection_targets(*, tokens: list[str]) -> list[str]:
    """Return paths introduced by shell redirection operators."""
    targets: list[str] = []
    redir = re.compile(r"^[0-9]*>>?$")
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if _FD_DUP_REDIR.match(tok):
            idx += 1
            continue
        if tok in (">&", "<&") and idx + 1 < len(tokens) and _FD_DUP_TARGET.match(tokens[idx + 1]):
            idx += 2
            continue
        if redir.match(tok) and idx + 1 < len(tokens):
            targets.append(tokens[idx + 1])
        else:
            # combined form `>file` / `>>file` (shlex may keep it joined)
            match = re.match(r"^[0-9]*>>?(.+)$", tok)
            if match and match.group(1):
                targets.append(match.group(1))
        idx += 1
    return targets


def _sed_targets(*, tokens: list[str]) -> list[str]:
    in_place = any(
        t == "-i" or t.startswith(("-i", "--in-place")) or t == "--in-place" for t in tokens[1:]
    )
    if not in_place:
        return []
    # the file operand(s) are the trailing non-option tokens
    return [tok for tok in tokens[1:] if not tok.startswith("-")]


def _command_targets(*, tokens: list[str]) -> list[str]:
    if not tokens:
        return []
    base = tokens[0].rsplit("/", 1)[-1]
    if base == "tee":
        return [tok for tok in tokens[1:] if not tok.startswith("-")]
    if base == "sed":
        return _sed_targets(tokens=tokens)
    if base == "dd":
        return [match.group(1) for tok in tokens[1:] if (match := re.match(r"^of=(.+)$", tok))]
    if base == "git":
        sub, _ = git_subcommand(tokens=tokens)
        if sub in ("apply", "am"):
            # writes into the current worktree; the cwd is the target
            return ["."]
    return []


def _redirect_targets_result(*, tokens: list[str]) -> Result[list[str], Exception]:
    """Collect candidate write-target paths from a shell segment.

    Best-effort, token/segment based:
      - redirections `> file` / `>> file` (also `1>`, `2>>`, etc.)
      - `tee [-a] file...`
      - `sed -i ... file` / `sed --in-place ... file`
      - `git apply` / `git am`            (writes into the cwd's worktree)
      - `dd of=file`

    Returns the raw path tokens (caller resolves them against cwd). Fails open
    (returns []) on anything it cannot confidently parse.
    """
    return Success([*_redirection_targets(tokens=tokens), *_command_targets(tokens=tokens)])


def redirect_targets(*, seg: str, tokens: list[str]) -> list[str]:
    if not seg.strip():
        return []
    result = _redirect_targets_result(tokens=tokens)
    if isinstance(result, Failure):
        _ = result.failure()
        return []
    return result.unwrap()
