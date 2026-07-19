#!/usr/bin/env python3
"""
livespec no-shadow-ledger — Stop hook warning on planning artifacts that
embed a checkbox task queue instead of deriving status from the ledger.

Shipped BYTE-IDENTICALLY by both Drivers (livespec-driver-claude at
.claude-plugin/hooks/, livespec-driver-codex at livespec/hooks/) as the
single-sourced neutral body; each Driver's hooks.json Stop entry is the
thin per-runtime adapter that invokes it. Codex consumes the Claude Stop
hook I/O format, so this one body serves both runtimes.

Declared on the `Stop` event. Scans the agent's last turn (the transcript
entries after the last REAL user message — tool-result deliveries do NOT
reset the window) for file-persisting tool calls (Write / Edit /
MultiEdit) that wrote a PLANNING ARTIFACT — a handoff, or any markdown
file under a plan/ or prompts/ directory. When such an artifact's written
content carries markdown checkbox task-list items ([ ] / [x]) at or above
a mechanical threshold, it emits a `systemMessage` WARNING on stdout.

WARN-ONLY BY CONTRACT (livespec core non-functional-requirements
"No shadow ledger"; contracts.md): this hook NEVER blocks the stop — it never
emits a `decision` key and never exits non-zero — and it never auto-edits
anything. The mechanical detection internals (the planning-artifact path
predicate, the checkbox threshold, the persisting-tool set) are Driver
implementation detail and MAY be tuned without a core spec cycle, per the
contract, provided the WARN-only Stop posture holds.

Fail-open contract: ANY failure (no python3 on PATH, malformed stdin,
missing/unreadable transcript, malformed transcript lines) is a silent
pass-through with exit 0.
"""

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from _vendor.returns.io import IOFailure, IOResult, IOSuccess
from _vendor.returns.result import Failure, Result, Success

# Mechanical "shadow-ledger smell" threshold: number of markdown checkbox
# task-list items in a single persisted planning artifact.
CHECKBOX_THRESHOLD = 3

# Tool calls that persist content to disk (NotebookEdit is excluded — a
# planning handoff is never a notebook).
PERSISTING_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})

# A markdown task-list item: a list bullet followed by a [ ] / [x] box. The
# anchor at line start keeps inline prose like `[ ]` (e.g. a rule quoting
# the forbidden syntax) from matching — only real list items count.
_CHECKBOX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[[ xX]\]")


def _is_real_user_entry(*, entry: dict) -> bool:
    """A user entry typed by the human — NOT a tool_result delivery."""
    if entry.get("type") != "user":
        return False
    message = entry.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    has_text = False
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_result":
            return False
        if block.get("type") == "text":
            has_text = True
    return has_text


def _written_text(*, name: str, tool_input: dict) -> str:
    """The content a persisting tool call wrote, aggregated to one string."""
    if name == "Write":
        text = tool_input.get("content")
        return text if isinstance(text, str) else ""
    if name == "Edit":
        text = tool_input.get("new_string")
        return text if isinstance(text, str) else ""
    if name == "MultiEdit":
        edits = tool_input.get("edits")
        parts: list[str] = []
        if isinstance(edits, list):
            for edit in edits:
                if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
                    parts.append(edit["new_string"])
        return "\n".join(parts)
    return ""


def _last_turn_writes(*, entries: list[dict]) -> list[tuple[str, str]]:
    """(path, written-text) pairs persisted after the last real user message."""
    start = 0
    for index, entry in enumerate(entries):
        if _is_real_user_entry(entry=entry):
            start = index + 1
    writes: list[tuple[str, str]] = []
    for entry in entries[start:]:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            name = block.get("name")
            if name not in PERSISTING_TOOLS:
                continue
            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                continue
            path = tool_input.get("file_path")
            if not isinstance(path, str) or not path:
                continue
            writes.append((path, _written_text(name=name, tool_input=tool_input)))
    return writes


def _is_planning_artifact(*, path: str) -> bool:
    """A handoff, or any markdown file under a plan/ or prompts/ directory."""
    lowered = path.lower()
    if not lowered.endswith(".md"):
        return False
    name = lowered.rsplit("/", 1)[-1]
    if "handoff" in name:
        return True
    segments = lowered.split("/")
    return "plan" in segments or "prompts" in segments


def _checkbox_count(*, text: str) -> int:
    return sum(1 for line in text.splitlines() if _CHECKBOX_RE.match(line))


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


def _transcript_entries(*, transcript: Path) -> IOResult[list[dict[str, object]] | None, Exception]:
    if not transcript.is_file():
        return IOSuccess(None)
    entries: list[dict[str, object]] = []
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return IOFailure(exc)
    for line in lines:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue  # fail-open per line: skip malformed transcript lines
        if isinstance(parsed, dict):
            entries.append(parsed)
    return IOSuccess(entries)


def _warning() -> IOResult[str | None, Exception]:
    """Return the systemMessage JSON, or None for a silent pass-through."""
    payload_result = _payload_from_stdin()
    if isinstance(payload_result, Failure):
        return IOFailure(payload_result.failure())
    payload = payload_result.unwrap()
    if payload is None or payload.get("stop_hook_active"):
        return IOSuccess(None)
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return IOSuccess(None)
    entries_result = _transcript_entries(transcript=Path(transcript_path))
    if isinstance(entries_result, IOFailure):
        return IOFailure(entries_result.failure())
    entries = entries_result.unwrap()
    if entries is None:
        return IOSuccess(None)
    for path, text in _last_turn_writes(entries=entries):
        if not _is_planning_artifact(path=path):
            continue
        count = _checkbox_count(text=text)
        if count >= CHECKBOX_THRESHOLD:
            message = (
                "livespec no-shadow-ledger WARN: this turn wrote a planning "
                f"artifact ({path}) carrying {count} checkbox task items "
                "([ ]/[x]). The no-shadow-ledger rule (livespec "
                'non-functional-requirements §"Planning Lane guidance") '
                "requires a handoff to derive status from the work-item ledger "
                "as its first action: each checklist item is a session-local "
                "step OR a pointer to a real ledger id, never a parallel work "
                "queue that shadows the ledger. Replace the embedded checkbox "
                "queue with ledger-id pointers and a ledger-status query."
            )
            return IOSuccess(json.dumps({"systemMessage": message}))
    return IOSuccess(None)


def main() -> int:
    """Hook entry point: emit the shadow-ledger WARN, if any; always exit 0.

    Owns the stdout write at the hook boundary and catches every failure so
    the Stop hook stays fail-open by contract — it NEVER blocks the stop and
    NEVER exits non-zero. Importable (no work at module import) so the hook
    body is testable in-process for real per-file coverage.
    """
    try:
        decision = _warning()
        if isinstance(decision, IOFailure):
            _ = decision.failure()
            return 0
        warning = decision.unwrap()
        if warning is not None:
            _ = sys.stdout.write(warning + "\n")
    except Exception:  # noqa: BLE001 — fail-open by contract
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
