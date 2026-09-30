"""Shared `.livespec.jsonc` project facts for the plugin-shipped hooks.

Two PreToolUse redirect hooks — `block_auto_memory.py` (auto-memory writes) and
`block_raw_bd_create.py` (raw `bd create` intake) — act ONLY inside a
livespec-governed project, and both name the ACTIVE impl-plugin's
`/<plugin>:capture-work-item` operation in their deny reason. That namespace is
a PROJECT FACT, declared by `.livespec.jsonc` `implementation.plugin` and NEVER
hardcoded in a hook body, so the resolution lives here ONCE instead of being
copied into each hook.

Reading it means parsing JSONC — JSON plus `//` line and `/* … */` block
comments, which the committed configs really do use — so the string-aware
comment stripper travels with the resolver.

Expected failures ride the `_result` railway instead of propagating. An absent
`.livespec.jsonc`, an unreadable or unparseable one, and one that declares no
`implementation.plugin` are all ordinary "this project is not identifiably
governed" answers for a hook whose contract is to pass through unless it
POSITIVELY identifies a governed project — never bugs.

Self-contained by contract: the plugin installer ships this file under bare
system `python3` with no virtualenv and no third-party packages, so every
import here is the standard library or the sibling `_result` railway module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from _result import Failure, Result, Success

__all__: list[str] = ["resolve_impl_plugin"]

_CONFIG_NAME = ".livespec.jsonc"


def _as_object_dict(*, value: object) -> dict[str, object] | None:
    """Narrow an arbitrary JSON value to a string-keyed dict, else None."""
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


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


def _declared_plugin(*, config_text: str) -> str | None:
    """The `implementation.plugin` value declared by a JSONC config, else None."""
    config = _as_object_dict(value=json.loads(_strip_jsonc_comments(text=config_text)))
    if config is None:
        return None
    implementation = _as_object_dict(value=config.get("implementation"))
    if implementation is None:
        return None
    plugin = implementation.get("plugin")
    if not isinstance(plugin, str) or not plugin.strip():
        return None
    return plugin.strip()


def resolve_impl_plugin(*, project_dir: str) -> Result[str, Exception]:
    """The active impl-plugin namespace from `<project_dir>/.livespec.jsonc`.

    Success carries the declared namespace; Failure carries the reason this
    project could not be identified as governed, which every caller collapses
    to a silent pass-through.
    """
    config_path = Path(project_dir) / _CONFIG_NAME
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        return Failure(exc)
    try:
        plugin = _declared_plugin(config_text=config_text)
    except ValueError as exc:
        return Failure(exc)
    if plugin is None:
        return Failure(LookupError(f"{config_path} declares no implementation.plugin"))
    return Success(plugin)
