#!/usr/bin/env python3
"""
Codex Stop hook enforcing structured livespec-overseer supervisor completion.

The hook is Driver-owned runtime control, not overseer-daemon semantic
judgment. It reads only structured supervisor markers and the optional user
transcript override command; it never parses assistant final-response text or
tmux pane text for completion evidence.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from _supervisor_producers import wake_producer_block_reason

__all__: list[str] = []

_MAX_MARKER_AGE = timedelta(hours=24)


def _block_payload(*, reason: str) -> str:
    message = (
        "livespec supervisor completion gate: continuing the session because "
        f"{reason}. While supervision_active is true, completion requires a "
        "fresh structured .supervisor-state marker with no open obligations, "
        "an explicit plan-complete disposition or exactly one maintainer-blocking "
        "question, and independently verified wake-producer evidence."
    )
    return json.dumps(
        {
            "decision": "block",
            "reason": message,
        }
    )


def _payload_from_stdin() -> dict[str, object] | None:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


def _find_project_dir() -> Path | None:
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".livespec.jsonc").is_file():
            return candidate
    return None


def _topic_from_payload(*, payload: dict[str, object]) -> str | None:
    for key in ("supervisor_topic", "topic"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _marker_paths(*, project_dir: Path, payload: dict[str, object]) -> tuple[list[Path], list[str]]:
    topic = _topic_from_payload(payload=payload)
    if topic is not None:
        marker = project_dir / "tmp" / "overseer" / topic / ".supervisor-state"
        return ([marker] if marker.is_file() else []), ([] if marker.is_file() else [topic])
    overseer_dir = project_dir / "tmp" / "overseer"
    if not overseer_dir.is_dir():
        return [], []
    markers = sorted(overseer_dir.glob("*/.supervisor-state"))
    return markers, []


def _read_marker(*, marker: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        parsed = json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "malformed marker"
    except OSError:
        return None, "unreadable marker"
    if not isinstance(parsed, dict):
        return None, "malformed marker"
    return cast("dict[str, object]", parsed), None


def _parse_updated_at(*, value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _staleness_reason(*, state: dict[str, object]) -> str | None:
    updated_at = _parse_updated_at(value=state.get("updated_at"))
    if updated_at is None:
        return "malformed marker timestamp"
    now = datetime.now(tz=timezone.utc)
    if updated_at > now + timedelta(minutes=5):
        return "stale marker timestamp"
    if now - updated_at > _MAX_MARKER_AGE:
        return "stale marker"
    return None


def _completion_reason(*, state: dict[str, object]) -> str | None:
    obligations = state.get("open_obligations")
    if not isinstance(obligations, list):
        return "malformed marker obligations"
    if obligations:
        return "open obligations remain"
    disposition = state.get("completion_disposition")
    if not isinstance(disposition, dict):
        return "malformed completion disposition"
    disposition_dict = cast("dict[str, object]", disposition)
    kind = disposition_dict.get("kind")
    question = disposition_dict.get("question")
    if kind == "plan-complete" and question in (None, ""):
        return None
    if kind == "maintainer-blocking" and isinstance(question, str):
        stripped = question.strip()
        if stripped.endswith("?") and stripped.count("?") == 1:
            return None
        return "exactly one maintainer question is required"
    if kind == "none":
        return "non-terminal disposition"
    return "unknown completion disposition"


def _last_real_user_text(*, transcript_path: object) -> str | None:
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    last_text: str | None = None
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            text = _user_text(entry=cast("dict[str, object]", entry))
            if text is not None:
                last_text = text
    return last_text


def _user_text(*, entry: dict[str, object]) -> str | None:
    if entry.get("type") != "user":
        return None
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    content = cast("dict[str, object]", message).get("content")
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in cast("list[object]", content):
        if not isinstance(block, dict):
            continue
        block_dict = cast("dict[str, object]", block)
        if block_dict.get("type") == "tool_result":
            return None
        if block_dict.get("type") == "text":
            text = block_dict.get("text")
            if isinstance(text, str):
                parts.append(text)
    joined = "\n".join(parts).strip()
    return joined or None


def _is_stop_override(*, payload: dict[str, object], topic: str) -> bool:
    text = _last_real_user_text(transcript_path=payload.get("transcript_path"))
    return text == f"stop supervising {topic}"


def _state_block_reason(
    *,
    project_dir: Path,
    payload: dict[str, object],
    marker: Path,
) -> str | None:
    state, read_reason = _read_marker(marker=marker)
    if read_reason is not None or state is None:
        return read_reason
    if state.get("supervision_active") is not True:
        return None
    topic = state.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        return "malformed marker topic"
    if _is_stop_override(payload=payload, topic=topic.strip()):
        return None
    marker_reason = _staleness_reason(state=state)
    completion_reason = _completion_reason(state=state)
    producer_reason = wake_producer_block_reason(
        project_dir=project_dir,
        topic=topic.strip(),
        producer=state.get("wake_producer"),
    )
    return marker_reason or completion_reason or producer_reason


def _decision() -> str | None:
    payload = _payload_from_stdin()
    if payload is None or payload.get("stop_hook_active") is True:
        return None
    project_dir = _find_project_dir()
    if project_dir is None:
        return None
    markers, missing_topics = _marker_paths(project_dir=project_dir, payload=payload)
    if missing_topics:
        return _block_payload(reason=f"missing marker for {', '.join(missing_topics)}")
    for marker in markers:
        reason = _state_block_reason(project_dir=project_dir, payload=payload, marker=marker)
        if reason is not None:
            return _block_payload(reason=reason)
    return None


def main() -> int:
    try:
        decision = _decision()
        if decision is not None:
            _ = sys.stdout.write(decision + "\n")
    except Exception:  # noqa: BLE001 — sole fail-closed guard boundary: deny per policy, exit 0
        _ = sys.stdout.write(_block_payload(reason="malformed marker or producer evidence") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
