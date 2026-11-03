"""Payload discovery and validation for the Codex Driver hook cache.

The half of the reconciler that answers "which payload is current, and is
it fit to alias?" — kept separate from the alias-topology half so neither
grows past the repo's per-file complexity ceiling. Sibling-imported by
`codex_hook_cache_reconcile`, stdlib-only for the same bare-`python3`
provisioning reason.
"""

from __future__ import annotations

import json
import py_compile
import re
import tempfile
from pathlib import Path

VERSION_RE = re.compile(r"^\d+(\.\d+){2}([-.][0-9A-Za-z.-]+)?$")
_PLUGIN_ROOT_TOKEN = "${CLAUDE_PLUGIN_ROOT}/"
_ENTRYPOINT_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s'\";|&]+)")


def version_sort_key(name: str) -> tuple[int, ...]:
    """Numeric ordering key for a version directory name."""
    numeric: list[int] = []
    for part in re.split(r"[-.]", name):
        if not part.isdigit():
            break
        numeric.append(int(part))
    return tuple(numeric)


def real_versions(*, root: Path) -> tuple[str, ...]:
    """Version-named real directories under `root`, oldest first.

    Symlinks are excluded on purpose: an alias is never evidence that a
    payload is present, and treating one as a version would let a dangling
    link masquerade as the current release.
    """
    if not root.is_dir():
        return ()
    found = [
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and not entry.is_symlink() and VERSION_RE.match(entry.name)
    ]
    return tuple(sorted(found, key=lambda name: (version_sort_key(name), name)))


def read_json(*, path: Path) -> tuple[dict[str, object] | None, str | None]:
    """Parse a JSON object file, returning `(parsed, problem)`."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        return None, f"{path}: unreadable ({err.strerror or err})"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        return None, f"{path}: invalid JSON ({err.msg} at line {err.lineno})"
    if not isinstance(parsed, dict):
        return None, f"{path}: expected a JSON object"
    return parsed, None


def declared_hook_scripts(*, payload: Path) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Entrypoints declared by the manifest and default hook registrations.

    Returns `(scripts, problems)`. The commands are read from the payload
    rather than from `codex plugin list`, whose `source.path` names the
    marketplace checkout and not the versioned cache the runtime executes.
    """
    registrations, problems = hook_registrations(payload=payload)
    scripts: list[Path] = []
    for path, events in registrations:
        for command in _walk_registered_commands(events=events):
            entrypoint, problem = _entrypoint_from_command(command=command)
            if problem:
                problems.append(f"{path}: {problem}")
            elif entrypoint is not None:
                scripts.append(payload / entrypoint)
    return tuple(dict.fromkeys(scripts)), tuple(problems)


def hook_registrations(*, payload: Path) -> tuple[list[tuple[Path, dict[str, object]]], list[str]]:
    """Read the union of manifest-selected and default hook registrations."""
    manifest_path = payload / ".codex-plugin" / "plugin.json"
    manifest, manifest_problem = read_json(path=manifest_path)
    if manifest is None:
        return [], [manifest_problem or f"{manifest_path}: unreadable"]
    paths = [payload / "hooks" / "hooks.json"]
    hooks_rel = manifest.get("hooks")
    if hooks_rel is not None:
        if not isinstance(hooks_rel, str) or not hooks_rel:
            return [], [f"{manifest_path}: malformed `hooks` entry"]
        paths.append(payload / hooks_rel)
    registrations: list[tuple[Path, dict[str, object]]] = []
    problems: list[str] = []
    for path in dict.fromkeys(paths):
        if path == paths[0] and not path.exists():
            continue
        registration, problem = read_json(path=path)
        if registration is None:
            problems.append(problem or f"{path}: unreadable")
            continue
        events = registration.get("hooks")
        if not isinstance(events, dict):
            problems.append(f"{path}: missing a `hooks` object")
            continue
        registrations.append((path, events))
    return registrations, problems


def declares_hooks(*, payload: Path) -> bool:
    """Whether the payload has any hook declaration, including a malformed one."""
    registrations, problems = hook_registrations(payload=payload)
    return bool(registrations or problems)


def _walk_registered_commands(*, events: dict[str, object]) -> list[str]:
    """Every hook command in a registration, independent of its event name."""
    found: list[str] = []
    for entries in events.values():
        if not isinstance(entries, list):
            continue
        for matcher in entries:
            if not isinstance(matcher, dict):
                continue
            for hook in matcher.get("hooks", []) or []:
                if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                    found.append(hook["command"])
    return found


def _entrypoint_from_command(*, command: str) -> tuple[str | None, str | None]:
    """Extract the first versioned path, rejecting malformed root mentions."""
    match = _ENTRYPOINT_RE.search(command)
    if match:
        return match.group(1), None
    if "CLAUDE_PLUGIN_ROOT" in command:
        return None, f"command {command!r} mentions CLAUDE_PLUGIN_ROOT without an entrypoint"
    return None, None


def validate_payload(*, payload: Path) -> tuple[str, ...]:
    """Problems that make `payload` unfit to be the target of `latest`.

    Every declared hook script must exist and compile under the same bare
    interpreter form Codex invokes it with; a payload that fails here is
    mid-write or broken, and aliasing to it would advertise hook
    continuity the runtime cannot deliver.
    """
    if not payload.is_dir():
        return (f"{payload}: payload directory is missing",)
    scripts, problems = declared_hook_scripts(payload=payload)
    if problems:
        return problems
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="livespec-hook-validate-") as scratch:
        for index, script in enumerate(scripts):
            if not script.is_relative_to(payload) or not script.is_file():
                failures.append(f"{script}: declared hook entrypoint is missing")
                continue
            try:
                py_compile.compile(
                    str(script), cfile=str(Path(scratch) / f"{index}.pyc"), doraise=True
                )
            except py_compile.PyCompileError as err:
                failures.append(f"{script}: does not compile under python3 ({err.msg.strip()})")
    return tuple(failures)
