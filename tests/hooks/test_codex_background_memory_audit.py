"""Unit tests for `livespec/hooks/codex_background_memory_audit.py`.

Codex's background memory database is outside the PreToolUse lifecycle, so the
Driver cannot block its creation the way `block_auto_memory.py` blocks manual
writes to `~/.codex/memories/`. The Stop-hook audit is therefore warn-only and
fail-open: it reads the background SQLite store in read-only mode, stays silent
for an empty store, and warns with the same durable-routing destinations when
background memory rows exist.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOK_SCRIPT = _REPO_ROOT / "livespec" / "hooks" / "codex_background_memory_audit.py"
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


@dataclass(frozen=True, kw_only=True)
class HookResult:
    returncode: int
    stdout: str
    stderr: str


def _load_hook_module():
    assert _HOOK_SCRIPT.is_file(), "Codex background-memory audit hook script must exist"
    spec = importlib.util.spec_from_file_location(
        "codex_background_memory_audit_under_test",
        str(_HOOK_SCRIPT),
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stop_input(*, transcript_path: str = "/tmp/transcript.jsonl", active: bool = False) -> str:
    return json.dumps({"transcript_path": transcript_path, "stop_hook_active": active})


def _run_hook(*, stdin: str, project_dir: Path | None, db_path: Path) -> HookResult:
    old_stdin = sys.stdin
    old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    old_db_path = os.environ.get("LIVESPEC_CODEX_BACKGROUND_MEMORY_DB")
    stdout = StringIO()
    stderr = StringIO()
    try:
        hook = _load_hook_module()
        sys.stdin = StringIO(stdin)
        if project_dir is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = str(project_dir)
        os.environ["LIVESPEC_CODEX_BACKGROUND_MEMORY_DB"] = str(db_path)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = hook.main()
    finally:
        sys.stdin = old_stdin
        if old_project_dir is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old_project_dir
        if old_db_path is None:
            os.environ.pop("LIVESPEC_CODEX_BACKGROUND_MEMORY_DB", None)
        else:
            os.environ["LIVESPEC_CODEX_BACKGROUND_MEMORY_DB"] = old_db_path
    return HookResult(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def _governed_project(*, tmp_path: Path, plugin: str = "livespec-orchestrator-beads-fabro") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "template": "livespec",
                "spec_root": "SPECIFICATION",
                "implementation": {"plugin": plugin},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _background_db(*, path: Path, jobs: int = 0, stage1_outputs: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute("create table jobs (id text primary key)")
        con.execute("create table stage1_outputs (id text primary key, output text)")
        for i in range(jobs):
            con.execute("insert into jobs (id) values (?)", (f"job-{i}",))
        for i in range(stage1_outputs):
            con.execute(
                "insert into stage1_outputs (id, output) values (?, ?)",
                (f"out-{i}", "durable guidance that belongs in AGENTS.md"),
            )
        con.commit()
    finally:
        con.close()
    return path


def _assert_pass(*, result: HookResult) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", result.stdout


def _assert_warn(*, result: HookResult) -> str:
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "expected warn-only systemMessage"
    payload = json.loads(result.stdout)
    assert "decision" not in payload
    message = payload["systemMessage"]
    assert isinstance(message, str)
    return message


def test_empty_background_memory_db_passes_silently(tmp_path: Path) -> None:
    project = _governed_project(tmp_path=tmp_path / "repo")
    db_path = _background_db(path=tmp_path / "home" / ".codex" / "memories_1.sqlite")

    result = _run_hook(stdin=_stop_input(), project_dir=project, db_path=db_path)

    _assert_pass(result=result)


def test_populated_background_memory_db_warns_with_durable_routes(tmp_path: Path) -> None:
    project = _governed_project(tmp_path=tmp_path / "repo", plugin="livespec-impl-custom")
    db_path = _background_db(
        path=tmp_path / "home" / ".codex" / "memories_1.sqlite",
        jobs=1,
        stage1_outputs=2,
    )

    result = _run_hook(stdin=_stop_input(), project_dir=project, db_path=db_path)

    message = _assert_warn(result=result)
    assert "memories_1.sqlite" in message
    assert "jobs=1" in message
    assert "stage1_outputs=2" in message
    assert "/livespec-impl-custom:capture-work-item" in message
    assert "/livespec:propose-change" in message
    assert "AGENTS.md" in message
    assert "Do NOT silently drop" in message


def test_background_memory_audit_fails_open_for_missing_or_malformed_db(tmp_path: Path) -> None:
    project = _governed_project(tmp_path=tmp_path / "repo")
    missing = tmp_path / "home" / ".codex" / "missing.sqlite"
    malformed = tmp_path / "home" / ".codex" / "memories_1.sqlite"
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text("not sqlite", encoding="utf-8")

    _assert_pass(result=_run_hook(stdin=_stop_input(), project_dir=project, db_path=missing))
    _assert_pass(result=_run_hook(stdin=_stop_input(), project_dir=project, db_path=malformed))


def test_background_memory_audit_skips_when_stop_hook_active(tmp_path: Path) -> None:
    project = _governed_project(tmp_path=tmp_path / "repo")
    db_path = _background_db(
        path=tmp_path / "home" / ".codex" / "memories_1.sqlite",
        jobs=1,
    )

    result = _run_hook(stdin=_stop_input(active=True), project_dir=project, db_path=db_path)

    _assert_pass(result=result)


def test_jsonc_comments_and_cwd_project_discovery(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    nested = project / "nested"
    nested.mkdir(parents=True)
    (project / ".livespec.jsonc").write_text(
        "{\n"
        "  // line comment\n"
        '  "template": "livespec",\n'
        '  "note": "escaped \\" quote",\n'
        "  /* block comment */\n"
        '  "implementation": { "plugin": "livespec-impl-jsonc" }\n'
        "}\n",
        encoding="utf-8",
    )
    db_path = _background_db(
        path=tmp_path / "home" / ".codex" / "memories_1.sqlite",
        stage1_outputs=1,
    )
    old_cwd = Path.cwd()
    try:
        os.chdir(nested)
        result = _run_hook(stdin=_stop_input(), project_dir=None, db_path=db_path)
    finally:
        os.chdir(old_cwd)

    message = _assert_warn(result=result)
    assert "/livespec-impl-jsonc:capture-work-item" in message


def test_background_memory_audit_passes_without_governed_project(tmp_path: Path) -> None:
    db_path = _background_db(
        path=tmp_path / "home" / ".codex" / "memories_1.sqlite",
        jobs=1,
    )

    result = _run_hook(stdin=_stop_input(), project_dir=tmp_path / "not-governed", db_path=db_path)

    _assert_pass(result=result)


def test_background_memory_audit_passes_when_no_project_is_discovered(tmp_path: Path) -> None:
    db_path = _background_db(
        path=tmp_path / "home" / ".codex" / "memories_1.sqlite",
        jobs=1,
    )
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = _run_hook(stdin=_stop_input(), project_dir=None, db_path=db_path)
    finally:
        os.chdir(old_cwd)

    _assert_pass(result=result)


def test_background_memory_audit_passes_for_non_mapping_payload(tmp_path: Path) -> None:
    project = _governed_project(tmp_path=tmp_path / "repo")
    db_path = _background_db(
        path=tmp_path / "home" / ".codex" / "memories_1.sqlite",
        jobs=1,
    )

    result = _run_hook(stdin="[]", project_dir=project, db_path=db_path)

    _assert_pass(result=result)


def test_background_memory_audit_passes_for_malformed_or_ungoverned_configs(
    tmp_path: Path,
) -> None:
    db_path = _background_db(
        path=tmp_path / "home" / ".codex" / "memories_1.sqlite",
        jobs=1,
    )
    for name, text in {
        "array": "[]",
        "missing-implementation": "{}",
        "bad-implementation": '{"implementation": []}',
        "blank-plugin": '{"implementation": {"plugin": "  "}}',
    }.items():
        project = tmp_path / name
        project.mkdir()
        (project / ".livespec.jsonc").write_text(text, encoding="utf-8")

        result = _run_hook(stdin=_stop_input(), project_dir=project, db_path=db_path)

        _assert_pass(result=result)


def test_background_memory_audit_treats_missing_stage1_table_as_empty(tmp_path: Path) -> None:
    project = _governed_project(tmp_path=tmp_path / "repo")
    db_path = tmp_path / "home" / ".codex" / "memories_1.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("create table jobs (id text primary key)")
        con.execute("insert into jobs (id) values ('job-1')")
        con.commit()
    finally:
        con.close()

    result = _run_hook(stdin=_stop_input(), project_dir=project, db_path=db_path)

    message = _assert_warn(result=result)
    assert "jobs=1" in message
    assert "stage1_outputs=0" in message


def test_background_memory_default_db_path_uses_codex_home(monkeypatch) -> None:
    hook = _load_hook_module()
    monkeypatch.delenv("LIVESPEC_CODEX_BACKGROUND_MEMORY_DB", raising=False)

    assert hook._background_db_path() == Path.home() / ".codex" / "memories_1.sqlite"


def test_background_audit_imports_without_the_repo_root_on_sys_path() -> None:
    """The audit hook must load from its own directory alone.

    Only `livespec/` is packaged, so the repo root does not exist in Codex's
    install cache. Importing with it removed from `sys.path` is the in-repo
    proxy for that layout; `tests/hooks/test_shipped_hooks_install_shape.py`
    asserts the same property against a real copied install tree.
    """
    old_path = list(sys.path)
    try:
        sys.path = [entry for entry in sys.path if entry != str(_REPO_ROOT)]
        hook = _load_hook_module()
    finally:
        sys.path = old_path

    assert not hasattr(hook, "_REPO_ROOT")
    assert hook.IOSuccess is hook.Success


def test_background_counts_returns_failure_when_sqlite_connect_raises(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hook = _load_hook_module()
    db_path = tmp_path / "memories_1.sqlite"
    db_path.write_text("", encoding="utf-8")

    def fail_connect(database: str, *, uri: bool):
        assert str(db_path) in database
        assert uri is True
        raise sqlite3.Error("boom")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)

    result = hook._background_counts(db_path=db_path)

    assert isinstance(result, hook.IOFailure)


def test_background_memory_audit_fails_open_for_malformed_stdin(tmp_path: Path) -> None:
    project = _governed_project(tmp_path=tmp_path / "repo")
    db_path = _background_db(
        path=tmp_path / "home" / ".codex" / "memories_1.sqlite",
        jobs=1,
    )

    result = _run_hook(stdin="{", project_dir=project, db_path=db_path)

    _assert_pass(result=result)


def test_background_memory_audit_main_fails_open_when_decision_raises(
    monkeypatch,
    capsys,
) -> None:
    hook = _load_hook_module()

    def explode():
        raise RuntimeError("boom")

    monkeypatch.setattr(hook, "_warning_decision", explode)

    assert hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
