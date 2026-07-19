#!/usr/bin/env python3
"""
tmux fleet-kill hazard classification for the livespec footgun guard.

Codex agents share the host's default tmux socket namespace, so any command
that reaches `/tmp/tmux-<uid>/default` with a `kill-server` — or that `pkill`s
the tmux binary — destroys every unrelated agent session on the host. This
module owns the decision "does this ONE shell segment reach that hazard?", so
`livespec_footgun_guard.py` keeps only the per-segment dispatch and the deny
emission.

THE DESIGN RULE: scan EVERY token position for a command head, never just
position 0.

An earlier guard peeled a closed allowlist of wrapper prefixes (`env`, `sudo`,
`nice`, `timeout`, …) and then inspected `tokens[0]`. That shape is unfixable by
extension: anything that displaces `tmux` off position 0 passes, and the set of
things that can do so is open-ended — every prefix nobody thought of is a live
bypass. Scanning all positions inverts the burden. A wrapper no longer has to be
KNOWN to be defeated; it merely has to leave a recognizable `tmux` / `pkill` /
`killall` / `kill` token somewhere in the segment, which every wrapper does,
because leaving that token is what a wrapper is for.

Quoting is what keeps this from over-blocking. `echo 'tmux kill-server'` lexes
to ONE token whose value is the whole sentence, so no token's basename is
`tmux`; the same holds for a `git commit -m` message, a `grep` pattern, a
here-doc body, and a `python3 -c` string. The accepted cost is that an UNQUOTED
mention (`echo tmux kill-server`) denies — a bias toward the deny direction,
since the opposite bias is what killed the fleet.

Four further evasion routes are closed here:

  - **Grouping punctuation.** `(tmux kill-server)` and `{ tmux kill-server; }`
    fuse the paren or brace onto the adjacent token, so `(){}` is stripped from
    each token's edges before the basename test.
  - **Nested payloads.** `sh -lc '<payload>'`, `bash -ctmux' kill-server'`,
    `eval '<payload>'`, and `xargs tmux` move the hazard one level down. Each is
    unwrapped and re-classified, and exceeding the depth budget fails CLOSED —
    nothing legitimate nests five `bash -c` deep, so exhausting the budget is
    evidence of evasion rather than a reason to allow.
  - **Socket-path spellings.** `/tmp/tmux-1000//default`,
    `/tmp/tmux-1000/../tmux-1000/default`, `/tmp/./tmux-1000/./default`, and
    `/tmp/tmux-1000/default/` all name the fleet socket. `-S` values are
    normalized LEXICALLY (never `realpath`, which would touch the filesystem
    from a hook) before being judged.
  - **Scope-flag precedence.** tmux(1): "If -S is specified, the default socket
    directory is not used and any -L flag is ignored." So `-S` beats `-L` NO
    MATTER the order, and among repeats the last of a kind wins. A guard that
    stopped at the first scope flag it saw allowed
    `tmux -L scratch -S /tmp/tmux-1000/default kill-server`.

A `kill-server` reached through a command substitution the guard cannot
evaluate fails CLOSED, as does a hazard-shaped segment that will not tokenize.
"""

import os
import re
import shlex

from _footgun_shell import segments
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
_GROUPING = "(){}"
_KILL_SERVER = re.compile(r"\bkill-server\b")
_MAX_DEPTH = 4
_PROCESS_KILLERS = ("kill", "killall", "pkill")
_PROCESS_KILLER_WORD = re.compile(r"\b(?:pkill|killall)\b")
_SHELLS = ("bash", "dash", "ksh", "sh", "zsh")
# `-c`, `-lc`, `-ic`, `-lic` — any clustered shell flag ending in `c`.
_SHELL_COMMAND_FLAG = re.compile(r"^-[a-zA-Z]*c$")
_TMUX_WORD = re.compile(r"\btmux\b")
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


def _ungrouped(*, token: str) -> str:
    """Strip shell grouping punctuation fused onto a token's edges."""
    return token.strip(_GROUPING)


def _shell_payload(*, arguments: list[str]) -> str | None:
    """The inline script of a `sh -c` / `bash -lc` / `zsh -ic` invocation."""
    for index, token in enumerate(arguments):
        if _SHELL_COMMAND_FLAG.match(token):
            return arguments[index + 1] if index + 1 < len(arguments) else None
        if token.startswith("-c") and len(token) > 2:
            return token[2:]
    return None


def _socket_is_hazardous(*, socket: str) -> bool:
    """True when a `-S` value names the fleet socket or its namespace dir."""
    if not socket:
        return True
    if "/" not in socket:
        # A bare name resolves against the caller's cwd, which a hook cannot
        # know, so it can never be SHOWN to sit off the default namespace.
        return True
    # LEXICAL normalization only: collapses `//` and resolves `.`/`..` without
    # touching the filesystem, which a PreToolUse hook must never do.
    normalized = os.path.normpath(socket)
    if _basename(token=normalized) == "default":
        return True
    return bool(_DEFAULT_NAMESPACE.match(normalized))


def _label_is_hazardous(*, label: str) -> bool:
    if not label:
        return True
    return _basename(token=os.path.normpath(label)) == "default"


def _flag_values(*, arguments: list[str], flag: str) -> list[str]:
    """Every value given for `flag`, in `-S x`, `-Sx`, and `-S=x` spellings."""
    values: list[str] = []
    index = 0
    total = len(arguments)
    while index < total:
        token = arguments[index]
        if token == flag:
            values.append(arguments[index + 1] if index + 1 < total else "")
            index += 2
            continue
        if token.startswith(f"{flag}="):
            values.append(token[len(flag) + 1 :])
        elif token.startswith(flag):
            values.append(token[len(flag) :])
        index += 1
    return values


def _scope_permits_kill(*, arguments: list[str]) -> bool:
    """True ONLY when the EFFECTIVE tmux scope is explicit and non-default."""
    sockets = _flag_values(arguments=arguments, flag="-S")
    if sockets:
        return not _socket_is_hazardous(socket=sockets[-1])
    labels = _flag_values(arguments=arguments, flag="-L")
    if labels:
        return not _label_is_hazardous(label=labels[-1])
    return False


def _xargs_target(*, arguments: list[str]) -> list[str]:
    """The command `xargs` would run, with xargs' own flags consumed."""
    index = 0
    total = len(arguments)
    while index < total:
        token = arguments[index]
        if token == "--":
            index += 1
            break
        if not token.startswith("-") or token == "-":
            break
        index += 2 if token in _XARGS_FLAGS_WITH_ARG else 1
    return arguments[index:]


def _targets_tmux_process(*, arguments: list[str]) -> bool:
    """True when any argument mentions tmux at all.

    Deliberately a SUBSTRING test over every token, flags included. A word-
    boundary test that skipped flag-shaped arguments allowed `pkill -f '^tmux'`,
    `pkill -ftmux`, and `pkill -f 'tmux: server'` — every one of which matches
    the live server.
    """
    return any("tmux" in argument for argument in arguments)


def _nested_hazard(*, command: str, arguments: list[str], depth: int) -> tuple[bool, str]:
    """Recurse into a payload this token hands to another interpreter."""
    if command in _SHELLS:
        payload = _shell_payload(arguments=arguments)
        if payload is not None:
            return _command_is_hazard(command=payload, depth=depth + 1)
    if command == "eval" and arguments:
        return _command_is_hazard(command=" ".join(arguments), depth=depth + 1)
    return False, ""


def _direct_hazard(*, command: str, arguments: list[str]) -> bool:
    """Is THIS token a tmux/process-killer command head reaching the hazard?"""
    if command == "xargs":
        target = _xargs_target(arguments=arguments)
        if target and _basename(token=target[0]) == "tmux":
            return not _scope_permits_kill(arguments=target[1:])
    if command == "tmux" and "kill-server" in arguments:
        return not _scope_permits_kill(arguments=arguments)
    return command in _PROCESS_KILLERS and _targets_tmux_process(arguments=arguments)


def _tokens_are_hazard(*, tokens: list[str], depth: int) -> tuple[bool, str]:
    """Scan EVERY position for a hazardous command head."""
    for index, token in enumerate(tokens):
        command = _basename(token=token)
        arguments = tokens[index + 1 :]
        nested, reason = _nested_hazard(command=command, arguments=arguments, depth=depth)
        if nested:
            return True, reason
        if _direct_hazard(command=command, arguments=arguments):
            return True, TMUX_REASON
    return False, ""


def _looks_like_tmux_kill_hazard(*, seg: str) -> bool:
    return bool(
        _TMUX_WORD.search(seg) and (_KILL_SERVER.search(seg) or _PROCESS_KILLER_WORD.search(seg))
    )


def _segment_is_hazard(*, seg: str, depth: int) -> tuple[bool, str]:
    # A `kill-server` reached through a command substitution cannot be resolved
    # without executing it, so it fails CLOSED rather than tokenizing to a
    # harmless-looking leading word like `$(echo`.
    if _COMMAND_SUBSTITUTION.search(seg) and _KILL_SERVER.search(seg):
        return True, TMUX_PARSE_REASON
    try:
        tokens = shlex.split(seg, posix=True)
    except ValueError:
        if _looks_like_tmux_kill_hazard(seg=seg):
            return True, TMUX_PARSE_REASON
        return False, ""
    return _tokens_are_hazard(tokens=[_ungrouped(token=token) for token in tokens], depth=depth)


def _command_is_hazard(*, command: str, depth: int) -> tuple[bool, str]:
    """Classify a whole command line: a nested payload is not one segment.

    `sh -c 'cd /tmp && tmux kill-server'` carries a full command line inside a
    single token, so a payload is re-split into its own segments rather than
    analyzed as if it were one.
    """
    if depth > _MAX_DEPTH:
        # Out of budget with content still unexamined. Nothing legitimate nests
        # this deep, so exhaustion is evidence of evasion: fail CLOSED.
        return True, TMUX_PARSE_REASON
    for inner in segments(command=command):
        blocked, reason = _segment_is_hazard(seg=inner, depth=depth)
        if blocked:
            return True, reason
    return False, ""


def _check_segment_result(*, seg: str, depth: int) -> Result[tuple[bool, str], Exception]:
    return Success(_command_is_hazard(command=seg, depth=depth))


def check_tmux_segment(*, seg: str, depth: int = 0) -> tuple[bool, str]:
    """(blocked, reason) for one shell segment; unresolvable hazards deny."""
    result = _check_segment_result(seg=seg, depth=depth)
    if isinstance(result, Failure):
        _ = result.failure()
        return True, TMUX_PARSE_REASON
    return result.unwrap()
