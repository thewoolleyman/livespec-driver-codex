#!/usr/bin/env python3
"""
Agent-memory write detection for the auto-memory guard (`block_auto_memory.py`).

Two questions live here, both POSITIVE-identification only:

  - `is_memory_path` — does a path name a file inside an agent memory
    directory? Either the Codex local-memory store (`~/.codex/memories/`) or
    the Claude Code auto-memory layout (`~/.claude/projects/<slug>/memory/*.md`,
    recognised as a `.md` file whose immediate parent directory is `memory`,
    plus the `memory` directory itself under `~/.claude/projects/<slug>/` as a
    copy or move destination).
  - `command_writes_memory` — does a shell command, as written, WRITE into one?
    Each `;` `&&` `||` `|` `&` and newline segment is judged on its own, and the
    payload of a `sh -c` / `bash -c` wrapper is judged one level down (an `env`,
    `sudo`, `timeout`, ... prefix is stripped first). The recognised write forms
    are the ratified non-exhaustive minimum: output redirection (`>`, `>>`,
    `&>`, including a here-document redirected into such a path), `tee`,
    an in-place editor (`sed -i`, `perl -i`), a `cp` / `mv` / `install` / `ln` /
    `touch` / `truncate` destination, `dd of=`, and an inline interpreter
    program (`python3 -c`, `perl -e`, `node -e`) whose text names such a path
    together with a write-mode open.

Reads (`cat`, `grep`, `ls`, `head`, `find`) and removal (`rm`, the way a
migrated note is discharged) are never a write. A destination the guard cannot
read from the command text — a path computed at runtime, or assembled inside a
script file — is a STATED LIMIT: the guard does not guess, so it passes.
A segment that cannot be lexed is likewise not identified, keeping the
fail-open contract.

Self-contained by contract: the plugin installer ships this file under bare
system `python3` with no virtualenv and no third-party packages, so every
import here is the standard library or a sibling module.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from _footgun_shell import segments, strip_leading_noise
from _result import Failure, Result, Success

__all__: list[str] = ["command_writes_memory", "is_memory_path"]

_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_SHELL_COMMAND_FLAG = re.compile(r"^-[a-zA-Z]*c$")
_MAX_DEPTH = 3
# `>|` and `>>|` are bash's CLOBBER spellings of `>` and `>>`: the same write,
# with `noclobber` overridden. `shlex` with `punctuation_chars=True` lexes each
# as ONE token, so they belong here beside the plain forms rather than needing
# any separate handling.
_REDIRECT_OPERATORS = frozenset({">", ">>", ">|", ">>|", "&>", "&>>"})
_COPY_HEADS = frozenset({"cp", "mv", "install", "ln"})
_TARGET_DIRECTORY_FLAGS = ("-t", "--target-directory")
# Flags whose following word is NOT a written file (a size, a date, a ref file).
_ARGUMENT_FLAGS: dict[str, frozenset[str]] = {
    "touch": frozenset({"-r", "-d", "-t", "--reference", "--date"}),
    "truncate": frozenset({"-s", "-r", "--size", "--reference"}),
    "tee": frozenset(),
}
_INTERPRETER = re.compile(r"^(?:python(?:\d+(?:\.\d+)*)?|perl|node|ruby)$")
_PROGRAM_FLAGS = frozenset({"-c", "-e", "-E", "--eval"})
_PERL_IN_PLACE = re.compile(r"^-[a-zA-Z]*i")
# A memory path NAMED inside program text.
_MEMORY_TEXT = re.compile(r"\.codex/memories\b|/memory/[^\s'\"]*\.md")
# A write-mode open in Python, Perl, Node or Ruby program text.
_WRITE_OPEN = re.compile(
    r"""open\s*\([^)]*?['"][rbt]*[wax+][rbtwax+]*['"]"""
    r"""|open\s*\([^)]*mode\s*=\s*['"][^'"]*[wax+]"""
    r"""|\.write_(?:text|bytes)\s*\("""
    r"""|\b(?:writeFileSync|appendFileSync|writeFile|appendFile|createWriteStream)\s*\("""
    r"""|\bopen\s*\(?\s*(?:my\s+)?[$\w]+\s*,\s*['"]\s*\+?>"""
    r"""|\bFile\.write\s*\("""
)


def _expand_home(*, word: str) -> str:
    """Expand the home spellings a shell would expand before running the command."""
    home = str(Path.home())
    if word == "~" or word.startswith("~/"):
        return home + word[1:]
    for spelling in ("${HOME}", "$HOME"):
        if word.startswith(spelling):
            return home + word[len(spelling) :]
    return word


def _codex_store_roots() -> tuple[Path, ...]:
    store = Path.home() / ".codex" / "memories"
    return (store, store.resolve())


def _is_claude_memory_dir(*, target: Path) -> bool:
    """`~/.claude/projects/<slug>/memory` — the directory a note is copied into."""
    projects = target.parent.parent
    return (
        target.name == "memory"
        and projects.name == "projects"
        and projects.parent.name == ".claude"
    )


def is_memory_path(*, path_str: str) -> bool:
    """True iff the path names an agent memory directory or a file inside one."""
    if not path_str:
        return False
    written = Path(os.path.normpath(Path(_expand_home(word=path_str)).absolute()))
    # Both spellings: as written, and with symlinks followed.
    return any(_names_memory(target=target) for target in (written, written.resolve()))


def _names_memory(*, target: Path) -> bool:
    for root in _codex_store_roots():
        if target == root or root in target.parents:
            return True
    if target.suffix == ".md" and target.parent.name == "memory":
        return True
    return _is_claude_memory_dir(target=target)


def _tokens(*, seg: str) -> Result[list[str], Exception]:
    """Shell words with redirection operators split out as their own tokens."""
    lexer = shlex.shlex(seg, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return Success(list(lexer))
    except ValueError as exc:
        return Failure(exc)


def _split_redirections(*, tokens: list[str]) -> tuple[list[str], list[str]]:
    """(command words, redirection targets). A `>&1` fd duplication is not a file."""
    words: list[str] = []
    targets: list[str] = []
    index = 0
    total = len(tokens)
    while index < total:
        token = tokens[index]
        if token in _REDIRECT_OPERATORS or token in ("<", "<<", "<<<", ">&", "<&"):
            # A fd number fused before the operator (`2>`) lexes as its own word.
            if words and words[-1].isdigit():
                _ = words.pop()
            if index + 1 < total and token in _REDIRECT_OPERATORS:
                targets.append(tokens[index + 1])
            index += 2
            continue
        words.append(token)
        index += 1
    return words, targets


def _operands(*, arguments: list[str], skip_after: frozenset[str]) -> list[str]:
    found: list[str] = []
    index = 0
    total = len(arguments)
    while index < total:
        argument = arguments[index]
        if argument in skip_after:
            index += 2
            continue
        if not argument.startswith("-") or argument == "-":
            found.append(argument)
        index += 1
    return found


def _copy_destinations(*, arguments: list[str]) -> list[str]:
    """The destination of a `cp` / `mv` / `install` / `ln`: `-t DIR`, else the last operand."""
    for index, argument in enumerate(arguments):
        if argument in _TARGET_DIRECTORY_FLAGS and index + 1 < len(arguments):
            return [arguments[index + 1]]
        if argument.startswith("--target-directory="):
            return [argument.split("=", 1)[1]]
    operands = _operands(arguments=arguments, skip_after=frozenset())
    return operands[-1:] if len(operands) > 1 else []


def _program_text(*, arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments):
        if argument in _PROGRAM_FLAGS and index + 1 < len(arguments):
            return arguments[index + 1]
        if re.match(r"^-[a-zA-Z]*[ce]$", argument) and index + 1 < len(arguments):
            return arguments[index + 1]
    return None


def _interpreter_writes(*, head: str, arguments: list[str]) -> bool:
    in_place = head == "perl" and any(_PERL_IN_PLACE.match(a) for a in arguments)
    if in_place and any(is_memory_path(path_str=a) for a in arguments if not a.startswith("-")):
        return True
    program = _program_text(arguments=arguments)
    if program is None:
        return False
    return bool(_MEMORY_TEXT.search(program)) and bool(_WRITE_OPEN.search(program))


def _shell_payload(*, arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments):
        if _SHELL_COMMAND_FLAG.match(argument):
            return arguments[index + 1] if index + 1 < len(arguments) else None
    return None


def _written_paths(*, head: str, arguments: list[str]) -> list[str]:
    """The files a non-interpreter, non-shell command writes, read from its words."""
    if head in _ARGUMENT_FLAGS:
        return _operands(arguments=arguments, skip_after=_ARGUMENT_FLAGS[head])
    if head in _COPY_HEADS:
        return _copy_destinations(arguments=arguments)
    if head == "sed" and any(a.startswith(("-i", "--in-place")) for a in arguments):
        return _operands(arguments=arguments, skip_after=frozenset({"-e", "-f"}))
    if head == "dd":
        return [a[3:] for a in arguments if a.startswith("of=")]
    return []


def _segment_writes(*, seg: str, depth: int) -> bool:
    lexed = _tokens(seg=seg)
    if isinstance(lexed, Failure):
        _ = lexed.failure()
        return False
    words, redirect_targets = _split_redirections(tokens=lexed.unwrap())
    if any(is_memory_path(path_str=t) for t in redirect_targets):
        return True
    invocation, _lefthook_off = strip_leading_noise(tokens=words)
    if not invocation:
        return False
    head = invocation[0].rsplit("/", 1)[-1]
    arguments = invocation[1:]
    if head in _SHELLS:
        payload = _shell_payload(arguments=arguments)
        return payload is not None and _command_writes(command=payload, depth=depth + 1)
    if _INTERPRETER.match(head):
        return _interpreter_writes(head=head, arguments=arguments)
    return any(is_memory_path(path_str=p) for p in _written_paths(head=head, arguments=arguments))


def _command_writes(*, command: str, depth: int) -> bool:
    if depth > _MAX_DEPTH:
        return False
    return any(_segment_writes(seg=seg, depth=depth) for seg in segments(command=command))


def command_writes_memory(*, command: str) -> bool:
    """True iff the command, as written, positively writes into an agent memory directory."""
    return _command_writes(command=command, depth=0)
