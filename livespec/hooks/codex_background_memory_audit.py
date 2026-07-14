#!/usr/bin/env python3
"""
livespec Codex background-memory audit — Codex Stop hook.

Codex's primary memories are generated outside the PreToolUse lifecycle, so the
manual-write guard cannot intercept them. This hook reads the background memory
SQLite store in read-only mode at Stop time. In a livespec-governed project, a
populated background store emits a warning that routes durable guidance to the
project's durable homes instead of Codex's harness-private memory surface.

Fail-open contract: malformed stdin, stop-hook re-entry, missing or unreadable
DB, missing tables, malformed config, and any exception are silent pass-throughs
with exit 0. The hook never writes to the SQLite DB and never blocks Stop.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

__all__: list[str] = []

_BACKGROUND_DB_ENV = "LIVESPEC_CODEX_BACKGROUND_MEMORY_DB"
_DEFAULT_BACKGROUND_DB = Path.home() / ".codex" / "memories_1.sqlite"
_BACKGROUND_TABLES = ("jobs", "stage1_outputs")


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
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".livespec.jsonc").is_file():
            return str(candidate)
    return None


def _resolve_plugin_namespace(*, project_dir: str) -> str | None:
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


def _background_db_path() -> Path:
    override = os.environ.get(_BACKGROUND_DB_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_BACKGROUND_DB


def _sqlite_ro_uri(*, path: Path) -> str:
    return f"file:{quote(str(path), safe='/')}?mode=ro"


def _background_counts(*, db_path: Path) -> dict[str, int] | None:
    if not db_path.is_file():
        return None
    con = sqlite3.connect(_sqlite_ro_uri(path=db_path), uri=True)
    try:
        available = {
            row[0]
            for row in con.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }
        counts: dict[str, int] = {}
        for table in _BACKGROUND_TABLES:
            if table in available:
                row = con.execute(f"select count(*) from {table}").fetchone()
                counts[table] = int(row[0]) if row is not None else 0
            else:
                counts[table] = 0
        return counts
    finally:
        con.close()


def _warning_payload(*, namespace: str, db_path: Path, counts: dict[str, int]) -> str:
    jobs = counts.get("jobs", 0)
    outputs = counts.get("stage1_outputs", 0)
    message = (
        "This project is livespec-governed. Codex background memory "
        f"({db_path}) contains entries (jobs={jobs}, "
        f"stage1_outputs={outputs}). Codex background memory is "
        "harness-private, per-user, and not a durable home for project guidance. "
        "Do NOT silently drop or rely on that memory; audit anything durable and "
        "route it by what it IS:\n"
        f"  - Trackable work (task/bug/refactor/follow-up) -> file in the beads "
        f"ledger via /{namespace}:capture-work-item.\n"
        "  - A spec-level rule or behavior -> /livespec:propose-change.\n"
        "  - Durable agent guidance / a learned preference / a convention -> "
        "capture in AGENTS.md, or in a focused .ai/<topic>.md file that "
        "AGENTS.md references.\n"
        "  - ONLY genuinely session-only, throwaway notes that matter nowhere "
        "outside this session may be dropped."
    )
    return json.dumps({"systemMessage": message})


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
        if payload.get("stop_hook_active") is True:
            return 0

        project_dir = _find_project_dir()
        if project_dir is None:
            return 0
        namespace = _resolve_plugin_namespace(project_dir=project_dir)
        if namespace is None:
            return 0

        db_path = _background_db_path()
        counts = _background_counts(db_path=db_path)
        if counts is None or sum(counts.values()) == 0:
            return 0
        sys.stdout.write(_warning_payload(namespace=namespace, db_path=db_path, counts=counts) + "\n")
    except Exception:  # noqa: BLE001 - fail-open by contract
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
