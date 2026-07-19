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

from _result import Failure, Result, Success

__all__: list[str] = ["segments", "strip_leading_noise", "git_subcommand"]

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GIT_GLOBAL_OPTS_WITH_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
_LINE_CONTINUATION = re.compile(r"\\\n")
_LEFTHOOK_OFF = re.compile(r"^LEFTHOOK=(?:0|false|off|no)$", re.IGNORECASE)
_DURATION = re.compile(r"^[0-9]+(?:\.[0-9]+)?[smhd]?$")
# Wrappers that merely re-exec another command, mapped to the flags of THEIRS
# that consume a following argument. Every one of them is a bypass if it is
# treated as the invocation instead of stripped: `env -i tmux kill-server` is
# strictly MORE dangerous than the bare form, because clearing the environment
# also clears the TMUX_TMPDIR scoping the caller may have relied on.
_WRAPPER_FLAGS_WITH_ARG: dict[str, tuple[str, ...]] = {
    "command": (),
    "env": ("-u", "-C", "--unset", "--chdir"),
    "exec": ("-a",),
    "ionice": ("-c", "-n", "-p", "-P", "-u"),
    "nice": ("-n", "--adjustment"),
    "nohup": (),
    "setsid": (),
    "stdbuf": ("-i", "-o", "-e", "--input", "--output", "--error"),
    "sudo": ("-u", "-g", "-U", "-C", "-p", "-r", "-t", "-T", "--user", "--group", "--prompt"),
    "time": ("-o", "-f", "--output", "--format"),
    "timeout": ("-s", "-k", "--signal", "--kill-after"),
}


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


def _join_line_continuations(*, command: str) -> str:
    """Fold `\\<newline>` the way a shell does, BEFORE anything splits on newline.

    `tmux \\<newline> kill-server` is ONE command to the shell. Splitting on the
    raw newline first would hand the analyzer two harmless-looking halves.
    """
    return _LINE_CONTINUATION.sub(" ", command)


def _split_on_operators(*, command: str) -> list[str]:
    """Split into shell segments on unquoted `;` `&&` `||` `|` `&` and newline.

    QUOTING-AWARE by construction. A regex split cuts inside quoted strings, so
    `echo 'first; tmux kill-server'` used to arrive as a segment beginning
    `tmux kill-server` — a false positive on text that is pure DATA. Quote state
    is tracked here so a separator inside quotes is never a separator.
    """
    found: list[str] = []
    current: list[str] = []
    quote = ""
    index = 0
    total = len(command)
    while index < total:
        char = command[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "\\" and index + 1 < total:
            current.append(char)
            current.append(command[index + 1])
            index += 2
            continue
        if command[index : index + 2] in ("&&", "||"):
            found.append("".join(current))
            current = []
            index += 2
            continue
        if char in ";|&\n":
            found.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    found.append("".join(current))
    return [segment.strip() for segment in found if segment.strip()]


def _segments_result(*, command: str) -> Result[list[str], Exception]:
    cleaned = _join_line_continuations(command=_strip_heredoc_bodies(command=command))
    return Success(_split_on_operators(command=cleaned))


def segments(*, command: str) -> list[str]:
    result = _segments_result(command=command)
    if isinstance(result, Failure):
        _ = result.failure()
        return []
    return result.unwrap()


def _skip_wrapper_arguments(*, tokens: list[str], start: int, base: str) -> int:
    """Index of the first token AFTER a wrapper's own flags and arguments."""
    flags_with_arg = _WRAPPER_FLAGS_WITH_ARG[base]
    index = start
    total = len(tokens)
    while index < total:
        token = tokens[index]
        if _ENV_ASSIGN.match(token):
            index += 1
            continue
        if token == "--":
            index += 1
            break
        if not token.startswith("-") or token == "-":
            break
        index += 2 if token in flags_with_arg else 1
    # `timeout` alone carries a bare positional DURATION before its command.
    if base == "timeout" and index < total and _DURATION.match(tokens[index]):
        index += 1
    return index


def _skip_mise_wrapper(*, tokens: list[str], start: int) -> int:
    """Index of the first token after a `mise exec [flags] [--]` prefix."""
    index = start + 1
    total = len(tokens)
    # `--` starts with `-`, so the terminator is consumed by this loop too.
    while index < total and (tokens[index] in ("exec", "x") or tokens[index].startswith("-")):
        index += 1
    return index


def _strip_leading_noise_result(*, tokens: list[str]) -> Result[tuple[list[str], bool], Exception]:
    """Strip leading env-assignments and every wrapper that merely re-execs.

    Returns (remaining tokens, lefthook_disabled_seen). Each strip RE-EXAMINES
    what remains, so stacked wrappers (`sudo env -i timeout 5 <cmd>`) reduce to
    the real invocation rather than hiding it behind the outermost name.
    """
    index = 0
    total = len(tokens)
    changed = True
    while changed and index < total:
        changed = False
        while index < total and _ENV_ASSIGN.match(tokens[index]):
            index += 1
            changed = True
        if index >= total:
            break
        base = tokens[index].rsplit("/", 1)[-1]
        if base in _WRAPPER_FLAGS_WITH_ARG:
            index = _skip_wrapper_arguments(tokens=tokens, start=index + 1, base=base)
            changed = True
            continue
        if base == "mise":
            index = _skip_mise_wrapper(tokens=tokens, start=index)
            changed = True
    # The disable can sit at ANY position in the stripped prefix, including
    # inside a wrapper's own environment (`sudo env LEFTHOOK=0 git commit`).
    lefthook_off = any(_LEFTHOOK_OFF.match(token) for token in tokens[:index])
    return Success((tokens[index:], lefthook_off))


def strip_leading_noise(*, tokens: list[str]) -> tuple[list[str], bool]:
    result = _strip_leading_noise_result(tokens=tokens)
    if isinstance(result, Failure):
        _ = result.failure()
        return [], False
    return result.unwrap()


def _git_subcommand_result(*, tokens: list[str]) -> Result[tuple[str | None, list[str]], Exception]:
    """If tokens is a git invocation, return (subcommand, args_after_subcommand)."""
    if not tokens:
        return Success((None, []))
    if tokens[0].rsplit("/", 1)[-1] != "git":
        return Success((None, []))
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
        return Success((None, []))
    return Success((tokens[i], tokens[i + 1 :]))


def git_subcommand(*, tokens: list[str]) -> tuple[str | None, list[str]]:
    result = _git_subcommand_result(tokens=tokens)
    if isinstance(result, Failure):
        _ = result.failure()
        return None, []
    return result.unwrap()
