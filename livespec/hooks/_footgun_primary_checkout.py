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

from _footgun_shell import git_subcommand

__all__: list[str] = ["is_primary_checkout", "redirect_targets", "PRIMARY_EDIT_REASON"]

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


def is_primary_checkout(*, path: str) -> bool:
    """True iff `path` resolves into a git repo that is its OWN primary checkout.

    A primary checkout is a repo whose `git config --get livespec.primaryPath`
    equals its own worktree root. Best-effort; fails CLOSED to False (treat as
    NOT a primary, i.e. fail open / do not block) on any uncertainty — a missing
    git, a non-repo path, a config without the key, or any subprocess error.
    """
    real = os.path.realpath(path)
    if real in _PRIMARY_CHECKOUT_CACHE:
        return _PRIMARY_CHECKOUT_CACHE[real]
    result = False
    try:
        toplevel = subprocess.run(
            ["git", "-C", real, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if toplevel.returncode == 0:
            worktree_root = os.path.realpath(toplevel.stdout.strip())
            primary = subprocess.run(
                ["git", "-C", real, "config", "--get", "livespec.primaryPath"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if primary.returncode == 0:
                declared = os.path.realpath(primary.stdout.strip())
                result = bool(declared) and declared == worktree_root
    except Exception:
        result = False  # fail open — never block on uncertainty
    _PRIMARY_CHECKOUT_CACHE[real] = result
    return result


def redirect_targets(*, seg: str, tokens: list[str]) -> list[str]:
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
    targets: list[str] = []

    # Redirections: a token matching `[0-9]*>` or `[0-9]*>>` introduces a file
    # target as the NEXT token. Scan the raw segment text for `>`/`>>` operators
    # since shlex keeps them as standalone tokens.
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
            m = re.match(r"^[0-9]*>>?(.+)$", tok)
            if m and m.group(1):
                targets.append(m.group(1))
        idx += 1

    if not tokens:
        return targets
    base = tokens[0].rsplit("/", 1)[-1]

    if base == "tee":
        for tok in tokens[1:]:
            if tok.startswith("-"):
                continue
            targets.append(tok)
    elif base == "sed":
        in_place = any(
            t == "-i" or t.startswith("-i") or t == "--in-place" or t.startswith("--in-place")
            for t in tokens[1:]
        )
        if in_place:
            # the file operand(s) are the trailing non-option tokens
            for tok in tokens[1:]:
                if not tok.startswith("-"):
                    targets.append(tok)
    elif base == "dd":
        for tok in tokens[1:]:
            m = re.match(r"^of=(.+)$", tok)
            if m:
                targets.append(m.group(1))
    elif base == "git":
        sub, _ = git_subcommand(tokens=tokens)
        if sub in ("apply", "am"):
            # writes into the current worktree; the cwd is the target
            targets.append(".")

    return targets
