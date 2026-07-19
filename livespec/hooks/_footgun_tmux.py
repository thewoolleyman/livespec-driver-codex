#!/usr/bin/env python3
"""
tmux fleet-kill hazard classification for the livespec footgun guard.

Codex agents share the host's default tmux socket namespace, so any command
that reaches `/tmp/tmux-<uid>/default` with a `kill-server` — or that `pkill`s
the tmux binary — destroys every unrelated agent session on the host. This
module owns the decision "does this ONE shell segment reach that hazard?", so
`livespec_footgun_guard.py` keeps only the per-segment dispatch and the deny
emission.

Classification is TOKEN based and evasion-aware. Three whole families of
bypass exist against a naive "does the segment start with `tmux`?" test, and
each is closed here:

  - **Wrapper prefixes.** `exec` / `command` / `nice` / `timeout` / `env -i` /
    `sudo` and friends all re-exec the real command under a different leading
    token. `strip_leading_noise` peels them and RE-EXAMINES what remains, so
    the wrapper cannot launder the invocation. `env -i` in particular must
    never read as safe: clearing the environment also clears any TMUX_TMPDIR
    scoping, making it strictly more dangerous than the bare form.
  - **Socket-path spellings.** `/tmp/tmux-1000//default`,
    `/tmp/tmux-1000/../tmux-1000/default`, and `/tmp/tmux-1000/default/` all
    name the fleet socket. `-S` values are normalized LEXICALLY (never
    `realpath`, which would touch the filesystem from a hook) before judging.
  - **Nested shell payloads.** `sh -lc '<payload>'`, `bash -c "<payload>"`,
    `zsh -ic '<payload>'`, and `xargs tmux` all move the hazard one level
    down. Each is unwrapped and re-classified to a bounded depth.

A segment carrying a tmux kill hazard that cannot be TOKENIZED fails CLOSED
(deny), as does one that reaches `kill-server` through a command substitution
the guard cannot evaluate. Only an EXPLICIT, non-default `-L`/`-S` scope
permits a `kill-server`.
"""

import os
import re
import shlex

from _footgun_shell import strip_leading_noise
from _result import Failure, Result, Success

__all__: list[str] = ["TMUX_PARSE_REASON", "TMUX_REASON", "check_tmux_segment"]

TMUX_REASON = (
    "NEVER run unscoped tmux fleet-kill commands from Codex. Codex agents "
    "share the host tmux socket namespace, so `tmux kill-server` on the "
    "default socket, `tmux -L default kill-server`, fleet `-S` socket kills, "
    "and `pkill`/`killall tmux` can terminate unrelated agents. Use an "
    "explicit non-default `tmux -L <agent-scope>` or `tmux -S <agent-socket>` "
    "target instead; TMUX_TMPDIR is not a safe scoping control."
)
TMUX_PARSE_REASON = (
    "BLOCKED because a command containing a tmux kill hazard could not parse "
    "safely. Codex agents share the host tmux socket namespace, so tmux kill "
    "hazards fail CLOSED; rewrite with a parseable, explicitly scoped "
    "non-default `tmux -L <agent-scope>` or `tmux -S <agent-socket>` command."
)

_COMMAND_SUBSTITUTION = re.compile(r"\$\(|`")
_DEFAULT_NAMESPACE = re.compile(r"^/tmp/tmux-\d+(?:/.*)?$")
_KILL_SERVER = re.compile(r"\bkill-server\b")
_MAX_DEPTH = 4
_PROCESS_KILLERS = ("pkill", "killall")
_SHELLS = ("bash", "dash", "ksh", "sh", "zsh")
# `-c`, `-lc`, `-ic`, `-lic` — any clustered shell flag ending in `c`.
_SHELL_COMMAND_FLAG = re.compile(r"^-[a-zA-Z]*c$")
_TMUX_PROCESS = re.compile(r"(?:^|[\s/])tmux(?:$|[\s/])")
_TMUX_WORD = re.compile(r"\btmux\b")
_PROCESS_KILLER_WORD = re.compile(r"\b(?:pkill|killall)\b")
_XARGS_FLAGS_WITH_ARG = (
    "-a",
    "-d",
    "-E",
    "-I",
    "-i",
    "-L",
    "-l",
    "-n",
    "-P",
    "-s",
    "--arg-file",
    "--delimiter",
    "--eof",
    "--max-args",
    "--max-chars",
    "--max-lines",
    "--max-procs",
    "--replace",
)


def _basename(*, token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _shell_payload(*, tokens: list[str]) -> str | None:
    """The inline script of a `sh -c` / `bash -lc` / `zsh -ic` invocation."""
    if not tokens or _basename(token=tokens[0]) not in _SHELLS:
        return None
    for index in range(1, len(tokens)):
        token = tokens[index]
        if _SHELL_COMMAND_FLAG.match(token):
            return tokens[index + 1] if index + 1 < len(tokens) else None
        if token.startswith("-c") and len(token) > 2:
            return token[2:]
    return None


def _socket_is_hazardous(*, socket: str) -> bool:
    """True when a `-S` value names the fleet socket or its namespace dir."""
    if not socket:
        return True
    # LEXICAL normalization only: collapses `//` and resolves `.`/`..` without
    # touching the filesystem, which a PreToolUse hook must never do.
    normalized = os.path.normpath(socket)
    if _basename(token=normalized) == "default":
        return True
    if "fleet" in normalized:
        return True
    return bool(_DEFAULT_NAMESPACE.match(normalized))


def _label_is_hazardous(*, label: str) -> bool:
    if not label:
        return True
    return _basename(token=os.path.normpath(label)) == "default"


def _flag_values(*, tokens: list[str], flag: str) -> list[str]:
    """Every value given for `flag`, in `-S x`, `-Sx`, and `-S=x` spellings."""
    values: list[str] = []
    index = 0
    total = len(tokens)
    while index < total:
        token = tokens[index]
        if token == flag:
            values.append(tokens[index + 1] if index + 1 < total else "")
            index += 2
            continue
        if token.startswith(f"{flag}="):
            values.append(token[len(flag) + 1 :])
        elif token.startswith(flag):
            values.append(token[len(flag) :])
        index += 1
    return values


def _scope_permits_kill(*, tokens: list[str]) -> bool:
    """True ONLY when an explicit, non-default `-L`/`-S` scope is named."""
    arguments = tokens[1:]
    labels = _flag_values(tokens=arguments, flag="-L")
    sockets = _flag_values(tokens=arguments, flag="-S")
    if any(_label_is_hazardous(label=label) for label in labels):
        return False
    if any(_socket_is_hazardous(socket=socket) for socket in sockets):
        return False
    return bool(labels or sockets)


def _xargs_target(*, tokens: list[str]) -> list[str] | None:
    """The command `xargs` would run, or None when this is not an xargs call."""
    if not tokens or _basename(token=tokens[0]) != "xargs":
        return None
    index = 1
    total = len(tokens)
    while index < total:
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if not token.startswith("-") or token == "-":
            break
        index += 2 if token in _XARGS_FLAGS_WITH_ARG else 1
    return tokens[index:]


def _targets_tmux_process(*, arguments: list[str]) -> bool:
    return any(_TMUX_PROCESS.search(argument) for argument in arguments)


def _check_tokens(*, tokens: list[str], depth: int) -> tuple[bool, str]:
    if depth > _MAX_DEPTH or not tokens:
        return False, ""
    payload = _shell_payload(tokens=tokens)
    if payload is not None:
        return check_tmux_segment(seg=payload, depth=depth + 1)
    target = _xargs_target(tokens=tokens)
    if target is not None:
        # `echo kill-server | xargs tmux` never carries `kill-server` in the
        # xargs segment itself, so an xargs call whose TARGET is tmux is a
        # hazard on its own unless it names an explicit non-default scope.
        if target and _basename(token=target[0]) == "tmux":
            return (False, "") if _scope_permits_kill(tokens=target) else (True, TMUX_REASON)
        return _check_tokens(tokens=target, depth=depth + 1)
    command = _basename(token=tokens[0])
    if command == "tmux" and "kill-server" in tokens[1:]:
        return (False, "") if _scope_permits_kill(tokens=tokens) else (True, TMUX_REASON)
    if command in _PROCESS_KILLERS and _targets_tmux_process(arguments=tokens[1:]):
        return True, TMUX_REASON
    return False, ""


def _looks_like_tmux_kill_hazard(*, seg: str) -> bool:
    return bool(
        _TMUX_WORD.search(seg)
        and (_KILL_SERVER.search(seg) or _PROCESS_KILLER_WORD.search(seg))
    )


def _check_segment_result(*, seg: str, depth: int) -> Result[tuple[bool, str], Exception]:
    # A `kill-server` reached through a command substitution cannot be resolved
    # without executing it, so it fails CLOSED rather than tokenizing to a
    # harmless-looking leading word like `$(echo`.
    if _COMMAND_SUBSTITUTION.search(seg) and _KILL_SERVER.search(seg):
        return Success((True, TMUX_PARSE_REASON))
    try:
        tokens = shlex.split(seg, posix=True)
    except ValueError:
        if _looks_like_tmux_kill_hazard(seg=seg):
            return Success((True, TMUX_PARSE_REASON))
        return Success((False, ""))
    core, _ = strip_leading_noise(tokens=tokens)
    return Success(_check_tokens(tokens=core, depth=depth))


def check_tmux_segment(*, seg: str, depth: int = 0) -> tuple[bool, str]:
    """(blocked, reason) for one shell segment; unresolvable hazards deny."""
    result = _check_segment_result(seg=seg, depth=depth)
    if isinstance(result, Failure):
        _ = result.failure()
        return True, TMUX_PARSE_REASON
    return result.unwrap()
