#!/usr/bin/env python3
"""
Shell-command tokenization primitives for the livespec footgun guard.

Extracted from `livespec_footgun_guard.py` (livespec epic livespec-i5ebqd,
file_lloc decomposition) as the cohesive shell-parsing sub-responsibility:
splitting a raw Bash command into inspectable segments (dropping here-doc
BODIES, which are file data), stripping leading env-assignment / `mise exec`
/ `sudo` / `env` noise, and recognizing a git invocation within a segment's
leading command.

BOTH the main guard (`livespec_footgun_guard.py`) and the primary-checkout-edit
detector (`_footgun_primary_checkout.py`) import from here; this module imports
from NEITHER (it is the leaf of the guard's three-module import DAG), so there
is no import cycle. Behavior is IDENTICAL to the pre-extraction inline helpers —
a pure cohesion move, not a logic change.
"""

import re

__all__: list[str] = ["segments", "strip_leading_noise", "git_subcommand"]

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GIT_GLOBAL_OPTS_WITH_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")


def _strip_heredoc_bodies(*, command: str) -> str:
    """Remove here-doc BODIES (they are file data, not executed commands).

    `cat > f <<'EOF'\n...body...\nEOF` — the body lines are data; analyzing them
    as command segments causes false positives. Keep the introducing line, drop
    everything from the next line through the terminator line.
    """
    lines = command.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        out.append(line)
        m = _HEREDOC.search(line)
        if m:
            term = m.group(1)
            i += 1
            # Skip body until a line that is exactly the terminator (optionally
            # indented for <<-).
            while i < n and lines[i].strip() != term:
                i += 1
            # `i` now points at the terminator line (or EOF); skip it too.
            if i < n:
                i += 1
            continue
        i += 1
    return "\n".join(out)


def segments(*, command: str) -> list[str]:
    cleaned = _strip_heredoc_bodies(command=command)
    return [s.strip() for s in _SEGMENT_SPLIT.split(cleaned) if s.strip()]


def strip_leading_noise(*, tokens: list[str]) -> tuple[list[str], bool]:
    """Strip leading env-assignments and `mise exec [--] ` / `sudo` / `env`.

    Returns (remaining tokens, lefthook_disabled_seen).
    """
    lefthook_off = False
    i = 0
    n = len(tokens)
    # Leading VAR=val assignments (env for the command).
    while i < n and _ENV_ASSIGN.match(tokens[i]):
        if re.match(r"^LEFTHOOK=(?:0|false|off|no)$", tokens[i], re.IGNORECASE):
            lefthook_off = True
        i += 1
    # `mise exec [flags] [--]` wrapper (possibly repeated with sudo/env).
    changed = True
    while changed and i < n:
        changed = False
        base = tokens[i].rsplit("/", 1)[-1]
        if base in ("sudo", "env"):
            i += 1
            changed = True
            while i < n and _ENV_ASSIGN.match(tokens[i]):
                i += 1
            continue
        if base == "mise":
            j = i + 1
            # consume `exec`, any flags, and a `--` terminator
            while (j < n and tokens[j] != "--" and tokens[j] in ("exec", "x")) or (
                j < n and tokens[j].startswith("-")
            ):
                j += 1
            if j < n and tokens[j] == "--":
                j += 1
            if j > i:
                i = j
                changed = True
            continue
    return tokens[i:], lefthook_off


def git_subcommand(*, tokens: list[str]) -> tuple[str | None, list[str]]:
    """If tokens is a git invocation, return (subcommand, args_after_subcommand)."""
    if not tokens:
        return None, []
    if tokens[0].rsplit("/", 1)[-1] != "git":
        return None, []
    i = 1
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            i += 1
            break
        if not t.startswith("-"):
            break
        i += 1
        if t in _GIT_GLOBAL_OPTS_WITH_ARG and i < n:
            i += 1
    if i >= n:
        return None, []
    return tokens[i], tokens[i + 1 :]
