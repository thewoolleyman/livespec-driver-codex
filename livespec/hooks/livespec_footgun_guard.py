#!/usr/bin/env python3
"""
livespec footgun guard — Codex PreToolUse hook (Bash/shell).

Shipped by livespec-driver-codex. Codex consumes the Claude PreToolUse hook
I/O format (stdin carries `tool_name` + `tool_input.command`; a
`hookSpecificOutput.permissionDecision: "deny"` payload on stdout blocks the
call), so this guard mirrors that shape verbatim.

Blocks ONLY patterns that are NEVER legitimate in the livespec family:
  - `git ... commit/push ... --no-verify`
  - `git ... config core.bare <true>`   (set; NOT --get/--unset/--list reads)
  - a leading `LEFTHOOK=0|false` env-assignment (the --no-verify equivalent)
  - a shell edit that would WRITE FILES AT A LIVESPEC PRIMARY CHECKOUT (a git
    repo whose `git config --get livespec.primaryPath` equals its own worktree
    root) — direct commits / edits at a primary checkout are refused; work in a
    secondary worktree instead
each with an actionable deny message naming the correct alternative.

Detection is TOKEN/SEGMENT based, not substring based. A real footgun is the
EXECUTED leading command of a shell segment — e.g. `git config core.bare true`
or `... && LEFTHOOK=0 git commit`. The dangerous strings frequently appear as
DATA (a test fixture, an `echo`, a `git log --grep`, a here-doc body, a commit
message); those must NOT be blocked. So for each `&&`/`||`/`;`/`|`/newline
segment we strip leading env-assignments + `mise exec --` + `sudo`/`env`
wrappers, then inspect only the resulting invocation. A segment whose leading
command is `echo`/`grep`/`python`/`cat`/etc. is never a commit/config footgun no
matter what string it carries.

This entry module owns the per-segment DECISION (`_check_segment`), the deny
emission, and the stdin/stdout main loop. Two cohesive sub-responsibilities are
extracted into sibling modules under this same `hooks/` directory (livespec epic
livespec-i5ebqd, file_lloc decomposition), imported below:
  - `_footgun_shell` — shell tokenization primitives (segment splitting,
    wrapper-prefix stripping, git-invocation recognition);
  - `_footgun_primary_checkout` — the "would this write files at a primary
    checkout?" detector (write-target extraction + primary-checkout probe);
  - `_footgun_tmux` — the evasion-aware tmux fleet-kill classifier (wrapper
    prefixes, `-S` socket-path normalization, nested shell/xargs payloads).

Always exits 0; fails OPEN on any parse/tokenize error (a guard bug must never
block legitimate work — the commit-refuse hook + branch protection are the real
backstops; this guard is only a fast early warning).
"""

import json
import re
import shlex
import sys
from pathlib import Path

from _footgun_primary_checkout import (
    PRIMARY_EDIT_REASON,
    is_allowed_primary_runtime_state,
    is_primary_checkout,
    redirect_targets,
)
from _footgun_shell import git_subcommand, segments, strip_leading_noise
from _footgun_tmux import TMUX_PARSE_REASON, check_tmux_segment
from _result import Failure, IOFailure, IOResult, IOSuccess, Result, Success

__all__: list[str] = []

_TMUX_HAZARD_HINT = re.compile(r"\b(?:kill-server|pkill|killall)\b")
_LITERAL_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(/.+)$")
_VARIABLE_TARGET = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")
_NO_VERIFY_REASON = (
    "NEVER use --no-verify in the livespec family. The lefthook gates "
    "(commit-msg, pre-commit, pre-push, Red-Green-Replay trailers) are "
    "load-bearing. If a hook rejects a commit, READ the rejection and fix the "
    "ROOT CAUSE, or HALT and ask the user — do not bypass. "
    "(memory feedback_sub_agent_dispatch_no_verify_ban)"
)
_CORE_BARE_REASON = (
    "NEVER set core.bare=true. Epic li-unbare eliminated the bare flag; "
    "core.bare on a primary is a REGRESSION the doctor invariant "
    "(primary-checkout-commit-refuse-hook-installed) forbids. Do edits in a "
    "secondary worktree via `git -C <repo> worktree add "
    "~/.worktrees/<repo>/<branch> -b <branch> origin/master`. "
    "(memory feedback_bare_flag_use_git_show_not_filesystem)"
)
_LEFTHOOK_REASON = (
    "NEVER set LEFTHOOK=0/false — it disables lefthook, a --no-verify "
    "equivalent. Fix the failing hook's root cause or HALT and ask. "
    "(memory feedback_sub_agent_dispatch_no_verify_ban)"
)


def _probe_path_for_target(*, target: str) -> str:
    """Directory path whose checkout status decides a write target."""
    target_path = Path(target)
    candidate = target_path if target_path.is_absolute() else Path.cwd() / target_path
    probe = candidate if candidate.is_dir() else candidate.parent
    return str(probe) or "."


def _literal_assignments(*, tokens: list[str], known: dict[str, str]) -> None:
    """Record literal absolute leading assignments for a later redirect target."""
    for token in tokens:
        match = _LITERAL_ASSIGNMENT.fullmatch(token)
        if match is None:
            break
        known[match.group(1)] = match.group(2)


def _resolved_target(*, target: str, known: dict[str, str]) -> str:
    """Resolve only a whole-target reference backed by a literal assignment."""
    match = _VARIABLE_TARGET.fullmatch(target)
    return known.get(match.group(1), target) if match is not None else target


def _primary_checkout_reason(*, seg: str, tokens: list[str], known: dict[str, str]) -> str | None:
    # (d) primary-checkout edit — checked on the RAW token stream BEFORE the
    # noise-strip, so redirections like `cmd > /primary/file` are seen.
    try:
        for target in redirect_targets(seg=seg, tokens=tokens):
            if target.startswith("-"):
                continue
            resolved_target = _resolved_target(target=target, known=known)
            candidate = Path(resolved_target)
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            is_primary = is_primary_checkout(path=_probe_path_for_target(target=resolved_target))
            is_runtime_state = is_allowed_primary_runtime_state(path=str(candidate))
            if is_primary and not is_runtime_state:
                return PRIMARY_EDIT_REASON
    # Path resolution can raise OSError; path probes can raise ValueError.
    except (OSError, ValueError):
        return None
    return None


def _git_config_reason(*, args: list[str]) -> str | None:
    # Reads/removes are fine; only a SET of core.bare to a truthy value is the footgun.
    if any(a in ("--get", "--unset", "--list", "--get-all", "--unset-all") for a in args):
        return None
    joined = " ".join(args)
    if any(a == "core.bare" for a in args) and any(
        re.fullmatch(r"(?:true|1|yes|on)", a, re.IGNORECASE) for a in args
    ):
        return _CORE_BARE_REASON
    # also catches `config core.bare=true`
    if re.search(r"\bcore\.bare\s*=\s*(?:true|1|yes|on)\b", joined, re.IGNORECASE):
        return _CORE_BARE_REASON
    return None


def _git_reason(*, tokens: list[str]) -> str | None:
    core, lefthook_off = strip_leading_noise(tokens=tokens)
    if lefthook_off:
        return _LEFTHOOK_REASON
    sub, args = git_subcommand(tokens=core)
    if sub is None:
        return None
    if sub in ("commit", "push") and "--no-verify" in args:
        return _NO_VERIFY_REASON
    if sub == "config":
        return _git_config_reason(args=args)
    return None


def _check_segment(*, seg: str, known: dict[str, str] | None = None) -> tuple[bool, str]:
    tmux_blocked, tmux_reason = check_tmux_segment(seg=seg)
    if tmux_blocked:
        return True, tmux_reason

    try:
        tokens = shlex.split(seg, posix=True)
    except ValueError:
        return False, ""  # non-tmux unparseable commands → fail open
    if not tokens:
        return False, ""

    known_assignments = {} if known is None else known
    _literal_assignments(tokens=tokens, known=known_assignments)
    reason = _primary_checkout_reason(
        seg=seg, tokens=tokens, known=known_assignments
    ) or _git_reason(tokens=tokens)
    return (True, reason) if reason is not None else (False, "")


def _deny_payload(*, reason: str, command: str) -> str:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"BLOCKED by livespec_footgun_guard.py (livespec-driver-codex)\n\n{reason}\n\n"
                f"Command: {command}\n\n"
                "This block is NOT a transient/transport failure. Do NOT retry "
                "the same command. Use the named alternative, or stop and ask "
                "the user. If this is a FALSE positive, tighten "
                "livespec-driver-codex's hooks/livespec_footgun_guard.py."
            ),
        }
    }
    return json.dumps(payload)


def _payload_from_raw(*, raw: str) -> Result[dict[str, object] | None, Exception]:
    if not raw.strip():
        return Success(None)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return Failure(exc)
    if not isinstance(parsed, dict):
        return Success(None)
    return Success(parsed)


def _command_from_payload(*, data: dict[str, object]) -> Result[str | None, Exception]:
    if data.get("tool_name", "") != "Bash":
        return Success(None)
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return Success(None)
    command = tool_input.get("command", "")
    if not isinstance(command, str) or not command:
        return Success(None)
    return Success(command)


def _decision(*, raw: str) -> IOResult[str | None, Exception]:
    payload_result = _payload_from_raw(raw=raw)
    if isinstance(payload_result, Failure):
        return IOFailure(payload_result.failure())
    data = payload_result.unwrap()
    if data is None:
        return IOSuccess(None)
    command_result = _command_from_payload(data=data)
    if isinstance(command_result, Failure):
        return IOFailure(command_result.failure())
    command = command_result.unwrap()
    if command is None:
        return IOSuccess(None)
    known: dict[str, str] = {}
    for seg in segments(command=command):
        blocked, reason = _check_segment(seg=seg, known=known)
        if blocked:
            return IOSuccess(_deny_payload(reason=reason, command=command))
    return IOSuccess(None)


def _fail_closed_on_hazard_hint(*, raw: str) -> int:
    """Deny a payload the guard could not parse when it CARRIES a tmux hazard.

    The guard fails OPEN in general — a guard bug must never block legitimate
    work. tmux fleet kills are the one exception: a malformed payload whose text
    still mentions `kill-server`/`pkill`/`killall` is exactly the shape an
    evasion takes, and allowing it costs every live agent session on the host.
    """
    if _TMUX_HAZARD_HINT.search(raw):
        _ = sys.stdout.write(_deny_payload(reason=TMUX_PARSE_REASON, command=raw[:200]) + "\n")
    return 0


def main() -> int:
    raw = ""
    try:
        raw = sys.stdin.read()
        decision = _decision(raw=raw)
        if isinstance(decision, IOFailure):
            _ = decision.failure()
            return _fail_closed_on_hazard_hint(raw=raw)
        payload = decision.unwrap()
        if payload is not None:
            _ = sys.stdout.write(payload + "\n")
        return 0
    except Exception:  # noqa: BLE001 — sole fail-closed guard boundary: deny per policy, exit 0
        return _fail_closed_on_hazard_hint(raw=raw)


if __name__ == "__main__":
    raise SystemExit(main())
