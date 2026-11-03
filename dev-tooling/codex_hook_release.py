"""Release-byte verification and declaration fingerprints for Codex hooks.

Verification scope.  Trust is recorded only when (a) every hook declaration equals the
release's, (b) every `${CLAUDE_PLUGIN_ROOT}/` entrypoint byte-matches the release, and
(c) every other file under each entrypoint's directory (its sibling helper modules)
byte-matches the release.  Stated limits: a module imported from outside every
entrypoint directory is covered only by Codex's plugin-wide content hash, not by a
byte comparison; and a command naming no `${CLAUDE_PLUGIN_ROOT}/` path references no
payload file, so its verified declaration text is its entire content.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from _codex_hook_cache_payload import hook_registrations

_EVENT_NAMES = {
    "PreToolUse": "pre_tool_use",
    "PermissionRequest": "permission_request",
    "PostToolUse": "post_tool_use",
    "PreCompact": "pre_compact",
    "PostCompact": "post_compact",
    "SessionStart": "session_start",
    "SessionEnd": "session_end",
    "UserPromptSubmit": "user_prompt_submit",
    "SubagentStart": "subagent_start",
    "SubagentStop": "subagent_stop",
    "Stop": "stop",
    "Interrupt": "interrupt",
}

# Codex ignores matcher values on Stop hooks.  Its persisted declaration
# fingerprint consequently omits them too; retaining an ignored matcher here
# would replace a valid trust record with one Codex does not recognize.
_MATCHER_EVENTS = frozenset(_EVENT_NAMES) - {"Stop"}


def verified_hook_keys(
    *, marketplace: str, plugin: str, payload: Path, release_payload: Path
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """Return persisted keys only when declarations and entrypoints match a release."""
    installed, installed_problems = hook_registrations(payload=payload)
    released, release_problems = hook_registrations(payload=release_payload)
    problems = _registration_problems(
        plugin=plugin,
        problems=tuple(installed_problems) + tuple(release_problems),
    )
    current = {_relative(path=path, root=payload): events for path, events in installed}
    release = {_relative(path=path, root=release_payload): events for path, events in released}
    hooks, declaration_problems = _matching_declarations(
        marketplace=marketplace, plugin=plugin, current=current, release=release
    )
    problems.extend(declaration_problems)
    problems.extend(
        _entrypoint_problems(plugin=plugin, payload=payload, release_payload=release_payload)
    )
    if problems:
        return (), untrusted_hook_problems(
            plugin=plugin,
            payload=payload,
            reason="release verification failed",
        )
    return tuple(hooks), ()


def untrusted_hook_problems(*, plugin: str, payload: Path, reason: str) -> tuple[str, ...]:
    """Name every installed hook when no release artifact can establish trust."""
    registrations, registration_problems = hook_registrations(payload=payload)
    labels: list[str] = []
    for path, events in registrations:
        relative = _relative(path=path, root=payload)
        labels.extend(_hook_labels(plugin=plugin, source_path=relative, events=events))
    if labels:
        return tuple(f"{label} ({reason})" for label in labels)
    return tuple(
        f"{plugin}: unverified hook {problem} ({reason})" for problem in registration_problems
    )


def _registration_problems(*, plugin: str, problems: tuple[str, ...]) -> list[str]:
    return [f"{plugin}: unverified hook {problem}" for problem in problems]


def _matching_declarations(
    *,
    marketplace: str,
    plugin: str,
    current: dict[str, dict[str, object]],
    release: dict[str, dict[str, object]],
) -> tuple[list[tuple[str, str]], list[str]]:
    hooks: list[tuple[str, str]] = []
    problems: list[str] = []
    for source_path, events in current.items():
        if release.get(source_path) != events:
            problems.extend(_hook_labels(plugin=plugin, source_path=source_path, events=events))
            continue
        entries, entry_problems = _hook_entries(
            marketplace=marketplace, plugin=plugin, source_path=source_path, events=events
        )
        hooks.extend(entries)
        problems.extend(entry_problems)
    for source_path, events in release.items():
        if source_path not in current:
            problems.extend(_hook_labels(plugin=plugin, source_path=source_path, events=events))
    return hooks, problems


def _hook_entries(
    *, marketplace: str, plugin: str, source_path: str, events: dict[str, object]
) -> tuple[list[tuple[str, str]], list[str]]:
    hooks: list[tuple[str, str]] = []
    problems: list[str] = []
    for event, groups in events.items():
        if not isinstance(groups, list) or event not in _EVENT_NAMES:
            problems.append(f"{plugin}: unverified hook {source_path}:{event}")
            continue
        for group_index, group in enumerate(groups):
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(handlers, list):
                problems.append(f"{plugin}: unverified hook {source_path}:{event}:{group_index}")
                continue
            for handler_index, handler in enumerate(handlers):
                key = _hook_key(
                    marketplace=marketplace,
                    plugin=plugin,
                    source_path=source_path,
                    event=event,
                    group_index=group_index,
                    handler_index=handler_index,
                )
                if not isinstance(handler, dict):
                    problems.append(f"{plugin}: unverified hook {key}")
                else:
                    hooks.append(
                        (key, _declaration_hash(event=event, group=group, handler=handler))
                    )
    return hooks, problems


def _entrypoint_problems(*, plugin: str, payload: Path, release_payload: Path) -> list[str]:
    problems: list[str] = []
    for entrypoint in _entrypoint_paths(payload=payload):
        release_path = release_payload / entrypoint.relative_to(payload)
        if not release_path.is_file() or entrypoint.read_bytes() != release_path.read_bytes():
            relative = entrypoint.relative_to(payload).as_posix()
            problems.append(f"{plugin}: unverified hook {relative}")
    for helper in _helper_files(payload=payload):
        release_path = release_payload / helper.relative_to(payload)
        if not release_path.is_file() or helper.read_bytes() != release_path.read_bytes():
            relative = helper.relative_to(payload).as_posix()
            problems.append(f"{plugin}: unverified hook {relative}")
    return problems


def _helper_files(*, payload: Path) -> tuple[Path, ...]:
    """Every file beside or beneath an entrypoint's directory, an import candidate."""
    helpers: dict[Path, None] = {}
    for directory in {entrypoint.parent for entrypoint in _entrypoint_paths(payload=payload)}:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                helpers[path] = None
    return tuple(helpers)


def _relative(*, path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _hook_labels(*, plugin: str, source_path: str, events: dict[str, object]) -> list[str]:
    return [f"{plugin}: unverified hook {source_path}:{event}" for event in events]


def _hook_key(
    *,
    marketplace: str,
    plugin: str,
    source_path: str,
    event: str,
    group_index: int,
    handler_index: int,
) -> str:
    return (
        f"{plugin}@{marketplace}:{source_path}:{_EVENT_NAMES[event]}:{group_index}:{handler_index}"
    )


def _declaration_hash(*, event: str, group: dict[str, object], handler: dict[str, object]) -> str:
    identity: dict[str, object] = {
        "event_name": _EVENT_NAMES[event],
        "hooks": [_normalized_handler(handler=handler)],
    }
    if event in _MATCHER_EVENTS and isinstance(group.get("matcher"), str):
        identity["matcher"] = group["matcher"]
    encoded = json.dumps(identity, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _normalized_handler(*, handler: dict[str, object]) -> dict[str, object]:
    if handler.get("type") != "command" or not isinstance(handler.get("command"), str):
        return handler
    normalized: dict[str, object] = {
        "type": "command",
        "command": handler["command"],
        "timeout": handler.get("timeout", 600),
        "async": handler.get("async", False),
    }
    for key in ("statusMessage", "additionalContextLimit"):
        if key in handler:
            normalized[key] = handler[key]
    return normalized


def _entrypoint_paths(*, payload: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for _, events in hook_registrations(payload=payload)[0]:
        for groups in events.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                handlers = group.get("hooks", []) if isinstance(group, dict) else []
                for handler in handlers:
                    command = handler.get("command") if isinstance(handler, dict) else None
                    if not isinstance(command, str) or "${CLAUDE_PLUGIN_ROOT}/" not in command:
                        continue
                    portion = command.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1]
                    paths.append(payload / portion.split()[0].strip("'\";|&"))
    return tuple(dict.fromkeys(paths))
