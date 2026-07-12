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

Always exits 0; fails OPEN on any parse/tokenize error (a guard bug must never
block legitimate work — the commit-refuse hook + branch protection are the real
backstops; this guard is only a fast early warning).
"""

import json
import os
import re
import shlex
import subprocess
import sys

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
_PRIMARY_EDIT_REASON = (
    "NEVER edit files directly at a livespec PRIMARY checkout (a repo whose "
    "`git config --get livespec.primaryPath` equals its own worktree root). "
    "Direct commits / writes at the primary are refused by the family "
    "commit-refuse hook. Do edits in a SECONDARY worktree via `git -C <repo> "
    "worktree add ~/.worktrees/<repo>/<branch> -b <branch> origin/master`, "
    "then PR → merge → cleanup. "
    "(memory feedback_dispatch_no_checkout_master_in_worktree)"
)

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GIT_GLOBAL_OPTS_WITH_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
_FD_DUP_TARGET = re.compile(r"^(?:[0-9]+|-)$")
_FD_DUP_REDIR = re.compile(r"^[0-9]*[<>]&(?:[0-9]+|-)$")

# Commands that, as the leading command of a segment, WRITE to a path argument.
# Each entry maps a command basename to a callable returning the candidate
# write-target tokens from its args (best-effort; fail open on anything odd).
_PRIMARY_CHECKOUT_CACHE: dict[str, bool] = {}


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


def _segments(*, command: str) -> list[str]:
    cleaned = _strip_heredoc_bodies(command=command)
    return [s.strip() for s in _SEGMENT_SPLIT.split(cleaned) if s.strip()]


def _strip_leading_noise(*, tokens: list[str]) -> tuple[list[str], bool]:
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


def _git_subcommand(*, tokens: list[str]) -> tuple[str | None, list[str]]:
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


def _is_primary_checkout(*, path: str) -> bool:
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


def _redirect_targets(*, seg: str, tokens: list[str]) -> list[str]:
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
        sub, _ = _git_subcommand(tokens=tokens)
        if sub in ("apply", "am"):
            # writes into the current worktree; the cwd is the target
            targets.append(".")

    return targets


def _check_segment(*, seg: str) -> tuple[bool, str]:
    try:
        tokens = shlex.split(seg, posix=True)
    except ValueError:
        return False, ""  # unparseable → fail open
    if not tokens:
        return False, ""

    # (d) primary-checkout edit — checked on the RAW token stream BEFORE the
    # noise-strip, so redirections like `cmd > /primary/file` are seen.
    try:
        for target in _redirect_targets(seg=seg, tokens=tokens):
            if target.startswith("-"):
                continue
            # Resolve the directory the write would land in.
            cand = target if os.path.isabs(target) else os.path.join(os.getcwd(), target)
            probe = cand if os.path.isdir(cand) else os.path.dirname(cand) or "."
            if _is_primary_checkout(path=probe):
                return True, _PRIMARY_EDIT_REASON
    except Exception:
        pass  # fail open

    core, lefthook_off = _strip_leading_noise(tokens=tokens)
    if lefthook_off:
        return True, _LEFTHOOK_REASON
    sub, args = _git_subcommand(tokens=core)
    if sub is None:
        return False, ""  # leading command isn't git → not a commit/config footgun
    if sub in ("commit", "push") and "--no-verify" in args:
        return True, _NO_VERIFY_REASON
    if sub == "config":
        # Reads/removes are fine; only a SET of core.bare to a truthy value is the footgun.
        if any(a in ("--get", "--unset", "--list", "--get-all", "--unset-all") for a in args):
            return False, ""
        joined = " ".join(args)
        if re.search(r"\bcore\.bare\b", joined) and re.search(
            r"\b(?:true|1|yes|on)\b", joined, re.IGNORECASE
        ):
            return True, _CORE_BARE_REASON
        # also catches `config core.bare=true`
        if re.search(r"\bcore\.bare\s*=\s*(?:true|1|yes|on)\b", joined, re.IGNORECASE):
            return True, _CORE_BARE_REASON
    return False, ""


def _deny(*, reason: str, command: str) -> None:
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
    print(json.dumps(payload))
    sys.exit(0)


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        data = json.loads(raw)
        if data.get("tool_name", "") != "Bash":
            sys.exit(0)
        command = data.get("tool_input", {}).get("command", "")
        if not command:
            sys.exit(0)
        for seg in _segments(command=command):
            blocked, reason = _check_segment(seg=seg)
            if blocked:
                _deny(reason=reason, command=command)
        sys.exit(0)
    except json.JSONDecodeError:
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
