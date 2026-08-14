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
_HOOK_EVENTS = ("PreToolUse", "Stop")
_PLUGIN_ROOT_TOKEN = "${CLAUDE_PLUGIN_ROOT}/"


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
    """Hook scripts the payload's own `hooks.json` declares for Codex to run.

    Returns `(scripts, problems)`. The commands are read from the payload
    rather than from `codex plugin list`, whose `source.path` names the
    marketplace checkout and not the versioned cache the runtime executes.
    """
    manifest_path = payload / ".codex-plugin" / "plugin.json"
    manifest, problem = read_json(path=manifest_path)
    if manifest is None:
        return (), (problem or f"{manifest_path}: unreadable",)
    hooks_rel = manifest.get("hooks")
    if not isinstance(hooks_rel, str) or not hooks_rel:
        return (), (f"{manifest_path}: manifest declares no `hooks` entry",)
    hooks_path = (payload / hooks_rel).resolve()
    registration, problem = read_json(path=hooks_path)
    if registration is None:
        return (), (problem or f"{hooks_path}: unreadable",)
    if "description" in registration:
        return (), (f"{hooks_path}: top-level `description` key is rejected by Codex",)
    events = registration.get("hooks")
    if not isinstance(events, dict):
        return (), (f"{hooks_path}: missing a `hooks` object",)
    scripts = [payload / rel for rel in _walk_registered_scripts(events=events)]
    if not scripts:
        return (), (f"{hooks_path}: declares no PreToolUse or Stop Python hook",)
    return tuple(dict.fromkeys(scripts)), ()


def _walk_registered_scripts(*, events: dict[str, object]) -> list[str]:
    """Every PreToolUse/Stop Python script path the registration names, in order."""
    found: list[str] = []
    for event in _HOOK_EVENTS:
        entries = events.get(event) or []
        if not isinstance(entries, list):
            continue
        for matcher in entries:
            for hook in (matcher or {}).get("hooks", []) or []:
                rel = _script_from_command(command=(hook or {}).get("command", ""))
                if rel is not None:
                    found.append(rel)
    return found


def _script_from_command(*, command: object) -> str | None:
    """Extract the plugin-root-relative script path Codex actually executes."""
    if not isinstance(command, str) or _PLUGIN_ROOT_TOKEN not in command:
        return None
    tail = command.split(_PLUGIN_ROOT_TOKEN, 1)[1]
    rel = tail.split('"', 1)[0].split("'", 1)[0].strip()
    return rel if rel.endswith(".py") else None


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
            if not script.is_file():
                failures.append(f"{script}: declared hook script is missing")
                continue
            try:
                py_compile.compile(
                    str(script), cfile=str(Path(scratch) / f"{index}.pyc"), doraise=True
                )
            except py_compile.PyCompileError as err:
                failures.append(f"{script}: does not compile under python3 ({err.msg.strip()})")
    return tuple(failures)
