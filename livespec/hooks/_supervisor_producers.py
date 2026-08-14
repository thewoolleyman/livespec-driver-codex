#!/usr/bin/env python3
"""Wake-producer verification for the supervisor completion Stop hook."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

__all__: list[str] = ["wake_producer_block_reason"]

_LOCAL_PRODUCER_KINDS = frozenset({"pane-watcher", "overseer-daemon"})
_REGISTERED_PRODUCER_KINDS = frozenset({"forge-ci", "ledger"})


def _string_field(*, data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _cold_reentry_reason(*, text: str | None, topic: str) -> str | None:
    if text is None:
        return "missing cold-open wake producer re-entry proof"
    lowered = text.lower()
    marker_tokens = (
        f"tmp/overseer/{topic}/.supervisor-state",
        ".supervisor-state",
    )
    if "cold-open" not in lowered or not any(token in lowered for token in marker_tokens):
        return "wake producer must cold-open from the supervisor marker"
    if "fresh" not in lowered or not any(token in lowered for token in ("ledger", "forge", "ci")):
        return "wake producer must re-query fresh ledger/forge state"
    return None


def _process_command_line(*, pid: int) -> str | None:
    if pid <= 0:
        return None
    cmdline = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = cmdline.read_bytes()
    except OSError:
        return None
    if not raw:
        return None
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")


def _local_producer_reason(*, producer: dict[str, object]) -> str | None:
    pid = producer.get("live_pid")
    expected_command = _string_field(data=producer, key="expected_command")
    identity = _string_field(data=producer, key="identity")
    if not isinstance(pid, int) or expected_command is None or identity is None:
        return "local wake producer requires live_pid, expected_command, and identity"
    command_line = _process_command_line(pid=pid)
    if command_line is None:
        return "wake producer pid is not live"
    if expected_command not in command_line or identity not in command_line:
        return "wake producer process identity does not match expected command and identity"
    return None


def _ids_from_sequence(*, values: list[object]) -> set[str]:
    identities: set[str] = set()
    for value in values:
        if isinstance(value, str) and value.strip():
            identities.add(value.strip())
        elif isinstance(value, dict):
            identity = _string_field(data=cast("dict[str, object]", value), key="identity")
            if identity is not None:
                identities.add(identity)
    return identities


def _ids_from_registry(*, data: object) -> set[str]:
    if isinstance(data, list):
        return _ids_from_sequence(values=cast("list[object]", data))
    if not isinstance(data, dict):
        return set()
    registry = cast("dict[str, object]", data)
    direct = registry.get("registered_producer_identities")
    if isinstance(direct, list):
        return _ids_from_sequence(values=cast("list[object]", direct))
    producers = registry.get("producers")
    if isinstance(producers, list):
        return _ids_from_sequence(values=cast("list[object]", producers))
    if isinstance(producers, dict):
        return {key for key in producers if key.strip()}
    return set()


def _registered_identities(*, project_dir: Path, topic: str) -> set[str]:
    paths = (
        project_dir / "tmp" / "overseer" / ".wake-producers.json",
        project_dir / "tmp" / "overseer" / topic / ".wake-producers.json",
    )
    identities: set[str] = set()
    for path in paths:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        identities.update(_ids_from_registry(data=parsed))
    return identities


def _registered_producer_reason(
    *,
    project_dir: Path,
    topic: str,
    producer: dict[str, object],
) -> str | None:
    identity = _string_field(data=producer, key="registered_producer_identity")
    if identity is None:
        return "unregistered wake producer"
    if identity not in _registered_identities(project_dir=project_dir, topic=topic):
        return "unregistered wake producer"
    return None


def wake_producer_block_reason(
    *,
    project_dir: Path,
    topic: str,
    producer: object,
) -> str | None:
    """Return a fail-closed reason when producer evidence is insufficient."""
    if not isinstance(producer, dict):
        return "malformed wake producer"
    producer_dict = cast("dict[str, object]", producer)
    kind = _string_field(data=producer_dict, key="kind")
    if kind is None or kind == "none":
        return "unknown wake producer"
    cold_reason = _cold_reentry_reason(
        text=_string_field(data=producer_dict, key="cold_reentry"),
        topic=topic,
    )
    if cold_reason is not None:
        return cold_reason
    if kind in _LOCAL_PRODUCER_KINDS:
        return _local_producer_reason(producer=producer_dict)
    if kind in _REGISTERED_PRODUCER_KINDS:
        return _registered_producer_reason(
            project_dir=project_dir,
            topic=topic,
            producer=producer_dict,
        )
    return "unknown wake producer"
