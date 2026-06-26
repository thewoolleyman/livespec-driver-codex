#!/usr/bin/env python3
"""
livespec auto-memory-write guard — Codex PreToolUse hook (Write/Edit).

Shipped by livespec-driver-codex. Mirrors the Claude Driver's
block-auto-memory guard for the Codex runtime: in a livespec-governed
project it intercepts a tool call that would write a file into the Codex
local-memory store (~/.codex/memories/) — a manual Write or Edit whose
target file_path resolves under that store — and emits
permissionDecision: deny with an intent-routing reason.

KNOWN LIMITATION: Codex's PRIMARY memories are background-generated and
OUTSIDE the pre_tool_use hook lifecycle; this guard covers only the
manual-write path through the Write and Edit tools.

Governance gate: CLAUDE_PROJECT_DIR env var (set by Claude Code and
compatible runtimes) is tried first; if absent the hook walks up from
cwd to locate .livespec.jsonc. A project is livespec-governed when
.livespec.jsonc exists and carries a non-empty `implementation.plugin`.
The namespace resolved from that key is used verbatim in the deny reason
and is NEVER hardcoded.

Fail-open contract: ANY failure (malformed stdin, unreadable or
unparseable .livespec.jsonc, missing env + no .livespec.jsonc reachable
from cwd, any exception) is a silent pass-through with exit 0. The hook
blocks ONLY when it POSITIVELY identifies a write into the Codex memory
store from a livespec-governed project.
"""

import json
import os
import sys
from pathlib import Path

__all__: list[str] = []

_CODEX_MEMORIES = Path.home() / ".codex" / "memories"

# File-write tools whose `tool_input.file_path` names the target file.
_FILE_WRITE_TOOLS = frozenset({"Write", "Edit"})


def _strip_jsonc_comments(*, text: str) -> str:
    """String-aware removal of // line and /* block */ comments."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _find_project_dir() -> str | None:
    """Locate the livespec-governed project root.

    Tries CLAUDE_PROJECT_DIR env var first (set by Claude Code and
    compatible runtimes); falls back to walking up from cwd looking
    for .livespec.jsonc. Returns None if neither approach succeeds.
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".livespec.jsonc").is_file():
            return str(candidate)
    return None


def _resolve_plugin_namespace(*, project_dir: str) -> str | None:
    """Return the impl plugin name from .livespec.jsonc, or None if not governed."""
    config_path = Path(project_dir) / ".livespec.jsonc"
    if not config_path.is_file():
        return None
    config = json.loads(
        _strip_jsonc_comments(text=config_path.read_text(encoding="utf-8"))
    )
    if not isinstance(config, dict):
        return None
    implementation = config.get("implementation")
    if not isinstance(implementation, dict):
        return None
    plugin = implementation.get("plugin")
    if not isinstance(plugin, str) or not plugin.strip():
        return None
    return plugin.strip()


def _target_file_path(*, payload: dict[str, object]) -> str | None:
    """Extract the write-target file_path from a tool-call payload, or None."""
    tool_name = payload.get("tool_name", "")
    if tool_name not in _FILE_WRITE_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    fp = tool_input.get("file_path")
    if not isinstance(fp, str) or not fp:
        return None
    return fp


def _is_under_memories(*, path_str: str) -> bool:
    """True iff the resolved path is under ~/.codex/memories/."""
    target = Path(path_str).expanduser().resolve()
    return target == _CODEX_MEMORIES or _CODEX_MEMORIES in target.parents


def _deny_payload(*, namespace: str) -> str:
    reason = (
        "This project is livespec-governed. Codex local-memory files "
        "(~/.codex/memories/) are NOT used here — ephemeral, per-user, and "
        "invisible to other agents/runtimes. Do NOT silently drop what you were about "
        "to write; route it by what it IS:\n"
        f"  - Trackable work (task/bug/refactor/follow-up) -> file in the beads ledger "
        f"via /{namespace}:capture-work-item.\n"
        "  - A spec-level rule or behavior -> /livespec:propose-change.\n"
        "  - Durable agent guidance / a learned preference / a convention -> capture in "
        "AGENTS.md, or (to avoid bloating AGENTS.md) in a focused instruction file "
        "that AGENTS.md references and that is loaded progressively/conditionally.\n"
        "  - ONLY genuinely session-only, throwaway notes that matter nowhere outside "
        "this session may be dropped."
    )
    return json.dumps(
        {
            "decision": "block",
            "reason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }
    )


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        payload: dict[str, object] = json.loads(raw)
        if not isinstance(payload, dict):
            sys.exit(0)
        path_str = _target_file_path(payload=payload)
        if path_str is None:
            sys.exit(0)
        if not _is_under_memories(path_str=path_str):
            sys.exit(0)
        # Positively identified a write into the Codex memory store.
        # Gate on governance before denying.
        project_dir = _find_project_dir()
        if project_dir is None:
            sys.exit(0)
        namespace = _resolve_plugin_namespace(project_dir=project_dir)
        if namespace is None:
            sys.exit(0)
        sys.stdout.write(_deny_payload(namespace=namespace) + "\n")
    except Exception:  # noqa: BLE001 — fail-open by contract
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
