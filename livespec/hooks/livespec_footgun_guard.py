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
import os
import re
import shlex
import sys

from _footgun_primary_checkout import (
    PRIMARY_EDIT_REASON,
    is_primary_checkout,
    redirect_targets,
)
from _footgun_shell import git_subcommand, segments, strip_leading_noise
from _footgun_tmux import check_tmux_segment
from _result import Failure, IOFailure, IOResult, IOSuccess, Result, Success

__all__: list[str] = []

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
def _check_segment(*, seg: str) -> tuple[bool, str]:
    tmux_blocked, tmux_reason = check_tmux_segment(seg=seg)
    if tmux_blocked:
        return True, tmux_reason

    try:
        tokens = shlex.split(seg, posix=True)
    except ValueError:
        return False, ""  # non-tmux unparseable commands → fail open
    if not tokens:
        return False, ""

    # (d) primary-checkout edit — checked on the RAW token stream BEFORE the
    # noise-strip, so redirections like `cmd > /primary/file` are seen.
    try:
        for target in redirect_targets(seg=seg, tokens=tokens):
            if target.startswith("-"):
                continue
            # Resolve the directory the write would land in.
            cand = target if os.path.isabs(target) else os.path.join(os.getcwd(), target)
            probe = cand if os.path.isdir(cand) else os.path.dirname(cand) or "."
            if is_primary_checkout(path=probe):
                return True, PRIMARY_EDIT_REASON
    # os.getcwd/os.path resolution can raise OSError; path probes can raise ValueError.
    except (OSError, ValueError):
        pass

    core, lefthook_off = strip_leading_noise(tokens=tokens)
    if lefthook_off:
        return True, _LEFTHOOK_REASON
    sub, args = git_subcommand(tokens=core)
    if sub is None:
        return False, ""  # leading command isn't git → not a commit/config footgun
    if sub in ("commit", "push") and "--no-verify" in args:
        return True, _NO_VERIFY_REASON
    if sub == "config":
        # Reads/removes are fine; only a SET of core.bare to a truthy value is the footgun.
        if any(a in ("--get", "--unset", "--list", "--get-all", "--unset-all") for a in args):
            return False, ""
        joined = " ".join(args)
        if any(a == "core.bare" for a in args) and any(
            re.fullmatch(r"(?:true|1|yes|on)", a, re.IGNORECASE) for a in args
        ):
            return True, _CORE_BARE_REASON
        # also catches `config core.bare=true`
        if re.search(r"\bcore\.bare\s*=\s*(?:true|1|yes|on)\b", joined, re.IGNORECASE):
            return True, _CORE_BARE_REASON
    return False, ""


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


def _payload_from_stdin() -> Result[dict[str, object] | None, Exception]:
    raw = sys.stdin.read()
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


def _decision() -> IOResult[str | None, Exception]:
    payload_result = _payload_from_stdin()
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
    for seg in segments(command=command):
        blocked, reason = _check_segment(seg=seg)
        if blocked:
            return IOSuccess(_deny_payload(reason=reason, command=command))
    return IOSuccess(None)


def main() -> int:
    try:
        decision = _decision()
        if isinstance(decision, IOFailure):
            _ = decision.failure()
            return 0
        payload = decision.unwrap()
        if payload is not None:
            print(payload)
        return 0
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
