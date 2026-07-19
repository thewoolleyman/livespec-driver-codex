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
import re
import sys
from pathlib import Path

from _result import Failure, IOFailure, IOResult, IOSuccess, Result, Success

__all__: list[str] = []

_CODEX_MEMORIES = Path.home() / ".codex" / "memories"

# File-write tools whose `tool_input.file_path` names the target file.
_FILE_WRITE_TOOLS = frozenset({"Write", "Edit"})

# Codex's primary file-edit tool. Its target paths live in the V4A patch body
# as `*** Add/Update/Delete File: <path>` (and `*** Move to: <path>`) markers;
# the tool_input field carrying the patch text is matched tolerantly.
_APPLY_PATCH_TOOLS = frozenset({"apply_patch"})
_PATCH_FILE_MARKER = re.compile(
    r"^\*\*\*\s+(?:Add|Update|Delete)\s+File:\s*(.+?)\s*$", re.MULTILINE
)
_PATCH_MOVE_MARKER = re.compile(r"^\*\*\*\s+Move\s+to:\s*(.+?)\s*$", re.MULTILINE)


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


def _collect_strings(*, obj: object) -> list[str]:
    """Recursively gather every string value within a JSON-ish object."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        out: list[str] = []
        for value in obj.values():
            out.extend(_collect_strings(obj=value))
        return out
    if isinstance(obj, list):
        nested: list[str] = []
        for value in obj:
            nested.extend(_collect_strings(obj=value))
        return nested
    return []


def _apply_patch_targets(*, tool_input: dict[str, object]) -> list[str]:
    """Extract V4A patch file-target paths from an apply_patch tool_input.

    Field-agnostic: scans every string value for `*** Add/Update/Delete File:`
    and `*** Move to:` markers, so the exact key carrying the patch text does
    not matter.
    """
    targets: list[str] = []
    for text in _collect_strings(obj=tool_input):
        targets.extend(_PATCH_FILE_MARKER.findall(text))
        targets.extend(_PATCH_MOVE_MARKER.findall(text))
    return targets


def _target_file_paths(*, payload: dict[str, object]) -> list[str]:
    """Return every write-target file path named by a tool-call payload.

    Write/Edit name a single `tool_input.file_path`; apply_patch (Codex's
    primary edit tool) names its targets in the V4A patch body.
    """
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    if tool_name in _FILE_WRITE_TOOLS:
        fp = tool_input.get("file_path")
        if isinstance(fp, str) and fp:
            return [fp]
        return []
    if tool_name in _APPLY_PATCH_TOOLS:
        return _apply_patch_targets(tool_input=tool_input)
    return []


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


def _decision() -> IOResult[str | None, Exception]:
    payload_result = _payload_from_stdin()
    if isinstance(payload_result, Failure):
        return IOFailure(payload_result.failure())
    payload = payload_result.unwrap()
    if payload is None:
        return IOSuccess(None)
    paths = _target_file_paths(payload=payload)
    if not paths:
        return IOSuccess(None)
    if not any(_is_under_memories(path_str=p) for p in paths):
        return IOSuccess(None)
    # Positively identified a write into the Codex memory store.
    # Gate on governance before denying.
    project_dir = _find_project_dir()
    if project_dir is None:
        return IOSuccess(None)
    namespace = _resolve_plugin_namespace(project_dir=project_dir)
    if namespace is None:
        return IOSuccess(None)
    return IOSuccess(_deny_payload(namespace=namespace))


def main() -> int:
    try:
        decision = _decision()
        if isinstance(decision, IOFailure):
            _ = decision.failure()
            return 0
        payload = decision.unwrap()
        if payload is not None:
            _ = sys.stdout.write(payload + "\n")
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
