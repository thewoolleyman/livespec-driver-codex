"""Release-verified Codex trust records for plugin hook payloads.

The Codex hook browser writes one declaration hash and one whole-plugin
content hash per hook below ``[hooks.state]``.  This module deliberately
supports only that observed record shape: a future Codex format is unsafe to
guess at, so callers receive a failure without any trust-state write.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
from pathlib import Path

from codex_hook_release import verified_hook_keys

_STATE_KEYS = {"enabled", "trusted_hash", "trusted_content_hash"}


@dataclasses.dataclass(frozen=True, kw_only=True)
class TrustReport:
    """Trust result for one covered plugin payload."""

    ok: bool
    trusted_hooks: tuple[str, ...]
    problems: tuple[str, ...]


def reconcile_trust(
    *,
    config_path: Path,
    marketplace: str,
    plugin: str,
    payload: Path,
    release_payload: Path,
) -> TrustReport:
    """Restore trust only after the payload's hook surface matches its release."""
    hooks, problems = verified_hook_keys(
        marketplace=marketplace,
        plugin=plugin,
        payload=payload,
        release_payload=release_payload,
    )
    if problems:
        return TrustReport(ok=False, trusted_hooks=(), problems=problems)
    config, problem = _read_recognized_state(config_path=config_path)
    if problem:
        return TrustReport(ok=False, trusted_hooks=(), problems=(f"{plugin}: {problem}",))
    content_hash, hash_problem = _plugin_content_hash(root=payload)
    if hash_problem:
        return TrustReport(ok=False, trusted_hooks=(), problems=(f"{plugin}: {hash_problem}",))
    _append_trust_records(
        config_path=config_path,
        existing=config,
        hooks=hooks,
        content_hash=content_hash,
    )
    return TrustReport(ok=True, trusted_hooks=tuple(key for key, _ in hooks), problems=())


def _read_recognized_state(*, config_path: Path) -> tuple[dict[str, object], str | None]:
    """Parse only the known hooks.state table format before mutating it."""
    try:
        text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    except OSError as err:
        return {}, f"unrecognized Codex trust record format ({err})"
    state: dict[str, object] = {}
    active_key: str | None = None
    for line in text.splitlines():
        active_key, table_problem = _state_table_key(line=line, active_key=active_key, state=state)
        if table_problem:
            return {}, table_problem
        if line.strip().startswith("["):
            continue
        if active_key is None or not line.strip() or line.lstrip().startswith("#"):
            continue
        field_problem = _add_state_field(line=line, entry=state[active_key])
        if field_problem:
            return {}, field_problem
    return state, None


def _state_table_key(
    *, line: str, active_key: str | None, state: dict[str, object]
) -> tuple[str | None, str | None]:
    """Recognize only a quoted Codex hook-state table key."""
    table = re.fullmatch(r'\[hooks\.state\.("(?:[^"\\]|\\.)*")\]', line.strip())
    if table is None:
        return (None, None) if line.strip().startswith("[") else (active_key, None)
    try:
        key = json.loads(table.group(1))
    except json.JSONDecodeError:
        return None, "unrecognized Codex trust record format"
    if not isinstance(key, str):
        return None, "unrecognized Codex trust record format"
    state[key] = {}
    return key, None


def _add_state_field(*, line: str, entry: object) -> str | None:
    """Validate one scalar field from the known hook-state schema."""
    match = re.fullmatch(r"([A-Za-z_]+)\s*=\s*(.+)", line.strip())
    if match is None or match.group(1) not in _STATE_KEYS or not isinstance(entry, dict):
        return "unrecognized Codex trust record format"
    try:
        value = json.loads(match.group(2))
    except json.JSONDecodeError:
        return "unrecognized Codex trust record format"
    if match.group(1) == "enabled" and not isinstance(value, bool):
        return "unrecognized Codex trust record format"
    if match.group(1) != "enabled" and not isinstance(value, str):
        return "unrecognized Codex trust record format"
    entry[match.group(1)] = value
    return None


def _plugin_content_hash(*, root: Path) -> tuple[str, str | None]:
    """Mirror Codex's deterministic bundle fingerprint for a stable payload."""
    digest = hashlib.sha256(b"codex-plugin-bundle-v1")
    try:
        for path in (root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())):
            name = path.name
            if name in {"__pycache__", ".venv"} or name.endswith((".pyc", ".egg-info")):
                continue
            relative = os.fsencode(path.relative_to(root).as_posix()) if path != root else b""
            digest.update(len(relative).to_bytes(8, "little"))
            digest.update(relative)
            if path.is_dir():
                digest.update(b"directory")
            elif path.is_file():
                data = path.read_bytes()
                digest.update(b"file")
                digest.update(len(data).to_bytes(8, "little"))
                digest.update(data)
            else:
                return "", f"unsupported plugin entry type: {path}"
    except OSError as err:
        return "", f"could not fingerprint plugin contents: {err}"
    return f"sha256:{digest.hexdigest()}", None


def _append_trust_records(
    *,
    config_path: Path,
    existing: dict[str, object],
    hooks: tuple[tuple[str, str], ...],
    content_hash: str,
) -> None:
    """Append only missing or stale state fields, preserving operator choices."""
    lines: list[str] = []
    for key, declaration_hash in hooks:
        state = existing.get(key, {})
        if not isinstance(state, dict):
            continue
        if (
            state.get("trusted_hash") == declaration_hash
            and state.get("trusted_content_hash") == content_hash
        ):
            continue
        lines.extend(
            (
                "",
                f"[hooks.state.{json.dumps(key)}]",
                f"trusted_hash = {json.dumps(declaration_hash)}",
                f"trusted_content_hash = {json.dumps(content_hash)}",
            )
        )
    if lines:
        with config_path.open("a", encoding="utf-8") as output:
            _ = output.write("\n".join(lines) + "\n")
