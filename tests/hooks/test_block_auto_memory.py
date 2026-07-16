"""Unit tests for `livespec/hooks/block_auto_memory.py`.

The guard is exercised exactly as Codex runs it: as a subprocess, with the
PreToolUse hook input JSON on stdin (`{"tool_name": "...", "tool_input": {...}}`)
and the `hookSpecificOutput.permissionDecision` payload read off stdout.
Codex consumes the Claude PreToolUse hook I/O format; a `"deny"` decision
blocks the call, an empty stdout + exit 0 lets it through.

Contract under test:

- DENY (permissionDecision: "deny", exit 0): a Write or Edit tool call whose
  target file_path resolves under `~/.codex/memories/`, when the current project
  is livespec-governed (carries `.livespec.jsonc` with `implementation.plugin`).
  The deny reason MUST route the would-be write BY INTENT — naming all four
  destinations — and MUST NOT silently drop durable guidance.
- PASS (empty stdout, exit 0): non-memories target path; non-governed project;
  Bash or other tool; no file_path in input; apply_patch with no memories path
  in patch content; empty or non-JSON stdin.
- FAIL-OPEN (empty stdout, exit 0): any exception, malformed stdin,
  unreadable/absent .livespec.jsonc.

The namespace used in the deny reason MUST match `implementation.plugin` from
the governed project's `.livespec.jsonc` — it is NEVER hardcoded.

Follows the family Python rules (keyword-only args via the leading `*`
separator, `from __future__ import annotations`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GUARD_SCRIPT = _REPO_ROOT / "livespec" / "hooks" / "block_auto_memory.py"
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import block_auto_memory  # noqa: E402 — path-dependent hook import.

_MEMORIES_PATH = Path.home() / ".codex" / "memories"

_LIVESPEC_JSONC_TEMPLATE = """{
  "template": "livespec",
  "spec_root": "SPECIFICATION",
  "implementation": { "plugin": "livespec-orchestrator-beads-fabro" }
}
"""

_LIVESPEC_JSONC_CUSTOM_PLUGIN = """{
  "template": "livespec",
  "spec_root": "SPECIFICATION",
  "implementation": { "plugin": "livespec-impl-custom" }
}
"""


@dataclass(frozen=True, kw_only=True)
class HookResult:
    returncode: int
    stdout: str
    stderr: str


def _write_input(*, tool_name: str, tool_input: dict[str, object]) -> str:
    return json.dumps({"tool_name": tool_name, "tool_input": tool_input})


def _run_guard(
    *,
    stdin: str,
    project_dir: str | None = None,
    cwd: Path | None = None,
) -> HookResult:
    old_stdin = sys.stdin
    old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    old_cwd = Path.cwd()
    stdout = StringIO()
    stderr = StringIO()
    try:
        sys.stdin = StringIO(stdin)
        if project_dir is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        if cwd is not None:
            os.chdir(cwd)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = block_auto_memory.main()
    finally:
        sys.stdin = old_stdin
        if old_project_dir is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old_project_dir
        os.chdir(old_cwd)
    return HookResult(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def _run_guard_subprocess(
    *,
    stdin: str,
    project_dir: str | None = None,
) -> subprocess.CompletedProcess[str]:
    # HOME must be propagated, not just PATH. The guard derives the memories
    # directory it protects from Path.home(), and so does this module's
    # _MEMORIES_PATH expectation — but Path.home() falls back to the passwd
    # entry when HOME is absent. Scrubbing HOME therefore made the subprocess
    # guard a DIFFERENT directory than the one the test targets, so the guard
    # matched nothing and emitted no decision. That stayed invisible wherever
    # HOME happens to equal the passwd home (GitHub-hosted runners, a plain
    # `docker run` as root) and only surfaced under the CI container hooks,
    # which run steps with HOME=/github/home while passwd still says /root.
    env = {"PATH": os.environ["PATH"], "HOME": str(Path.home())}
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    return subprocess.run(
        ["python3", str(_GUARD_SCRIPT)],
        input=stdin,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _assert_deny(*, result: HookResult | subprocess.CompletedProcess[str]) -> dict[str, object]:
    """Assert the guard emitted a `deny` decision and exited 0; return the payload."""
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "expected a decision payload on stdout, got empty"
    payload = json.loads(result.stdout)
    hook_output = payload["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    return payload


def _assert_pass(*, result: HookResult | subprocess.CompletedProcess[str]) -> None:
    """Assert the guard let the call through (empty stdout, exit 0)."""
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"expected silent pass-through; got {result.stdout!r}"


def _governed_project(*, tmp_path: Path, plugin: str = "livespec-orchestrator-beads-fabro") -> Path:
    """Create a minimal livespec-governed project directory."""
    config = json.dumps(
        {
            "template": "livespec",
            "spec_root": "SPECIFICATION",
            "implementation": {"plugin": plugin},
        }
    )
    (tmp_path / ".livespec.jsonc").write_text(config, encoding="utf-8")
    return tmp_path


def test_deny_write_to_codex_memories_when_governed(tmp_path: Path) -> None:
    """Write tool targeting ~/.codex/memories/foo.md in governed project → deny."""
    project = _governed_project(tmp_path=tmp_path)
    target = str(_MEMORIES_PATH / "foo.md")
    stdin = _write_input(
        tool_name="Write",
        tool_input={"file_path": target, "content": "some memory"},
    )
    result = _run_guard(stdin=stdin, project_dir=str(project))
    _assert_deny(result=result)


def test_subprocess_smoke_denies_write_to_codex_memories_when_governed(tmp_path: Path) -> None:
    """The shipped script path still speaks the Codex hook stdin/stdout protocol."""
    project = _governed_project(tmp_path=tmp_path)
    stdin = _write_input(
        tool_name="Write",
        tool_input={"file_path": str(_MEMORIES_PATH / "smoke.md"), "content": "some memory"},
    )
    result = _run_guard_subprocess(stdin=stdin, project_dir=str(project))
    _assert_deny(result=result)


def test_deny_edit_to_codex_memories_when_governed(tmp_path: Path) -> None:
    """Edit tool targeting ~/.codex/memories/bar.md in governed project → deny."""
    project = _governed_project(tmp_path=tmp_path)
    target = str(_MEMORIES_PATH / "bar.md")
    stdin = _write_input(
        tool_name="Edit",
        tool_input={
            "file_path": target,
            "old_string": "old",
            "new_string": "new",
        },
    )
    result = _run_guard(stdin=stdin, project_dir=str(project))
    _assert_deny(result=result)


def test_pass_write_to_non_memories_path_when_governed(tmp_path: Path) -> None:
    """Write tool targeting a non-memories path in governed project → pass."""
    project = _governed_project(tmp_path=tmp_path)
    stdin = _write_input(
        tool_name="Write",
        tool_input={"file_path": "/tmp/notes.md", "content": "scratch"},
    )
    result = _run_guard(stdin=stdin, project_dir=str(project))
    _assert_pass(result=result)


def test_pass_write_to_memories_when_not_governed(tmp_path: Path) -> None:
    """Write tool targeting memories path but project is NOT governed → pass."""
    # tmp_path has no .livespec.jsonc
    target = str(_MEMORIES_PATH / "foo.md")
    stdin = _write_input(
        tool_name="Write",
        tool_input={"file_path": target, "content": "some memory"},
    )
    result = _run_guard(stdin=stdin, project_dir=str(tmp_path))
    _assert_pass(result=result)


def test_pass_bash_tool_even_to_memories_path(tmp_path: Path) -> None:
    """Bash tool call (not a file-write tool) → pass even if command touches memories."""
    project = _governed_project(tmp_path=tmp_path)
    stdin = _write_input(
        tool_name="Bash",
        tool_input={"command": f"cat {_MEMORIES_PATH}/foo.md"},
    )
    result = _run_guard(stdin=stdin, project_dir=str(project))
    _assert_pass(result=result)


def test_pass_empty_stdin() -> None:
    """Empty stdin → fail-open pass."""
    result = _run_guard(stdin="")
    _assert_pass(result=result)


def test_pass_non_json_stdin() -> None:
    """Non-JSON stdin → fail-open pass."""
    result = _run_guard(stdin="not json at all")
    _assert_pass(result=result)


def test_pass_no_file_path_in_write_input(tmp_path: Path) -> None:
    """Write tool input without file_path → fail-open pass."""
    project = _governed_project(tmp_path=tmp_path)
    stdin = _write_input(
        tool_name="Write",
        tool_input={"content": "some content"},  # missing file_path
    )
    result = _run_guard(stdin=stdin, project_dir=str(project))
    _assert_pass(result=result)


def test_deny_reason_routes_by_intent_not_only_capture_work_item(tmp_path: Path) -> None:
    """Deny reason names all four intent routes; MUST NOT silently drop content."""
    project = _governed_project(tmp_path=tmp_path)
    target = str(_MEMORIES_PATH / "guidance.md")
    stdin = _write_input(
        tool_name="Write",
        tool_input={"file_path": target, "content": "durable guidance"},
    )
    result = _run_guard(stdin=stdin, project_dir=str(project))
    payload = _assert_deny(result=result)
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert isinstance(reason, str)
    # Route 1: trackable work → capture-work-item
    assert "capture-work-item" in reason
    # Route 2: spec-level rule → propose-change
    assert "propose-change" in reason or "/livespec:propose-change" in reason
    # Route 3: durable guidance → AGENTS.md (or instruction file)
    assert "AGENTS.md" in reason
    # Must not silently drop
    assert "silently drop" in reason or "Do NOT silently drop" in reason


def test_deny_reason_uses_plugin_namespace_from_config(tmp_path: Path) -> None:
    """Deny reason uses namespace from .livespec.jsonc, not a hardcoded value."""
    project = _governed_project(tmp_path=tmp_path, plugin="livespec-impl-custom")
    target = str(_MEMORIES_PATH / "note.md")
    stdin = _write_input(
        tool_name="Write",
        tool_input={"file_path": target, "content": "note"},
    )
    result = _run_guard(stdin=stdin, project_dir=str(project))
    payload = _assert_deny(result=result)
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert "livespec-impl-custom" in reason
    # The default plugin name must NOT appear when a different one is configured
    assert "livespec-orchestrator-beads-fabro" not in reason


def test_pass_no_project_dir_env() -> None:
    """No CLAUDE_PROJECT_DIR and no .livespec.jsonc reachable from cwd → pass."""
    target = str(_MEMORIES_PATH / "foo.md")
    stdin = _write_input(
        tool_name="Write",
        tool_input={"file_path": target, "content": "note"},
    )
    # Run with no CLAUDE_PROJECT_DIR and cwd set to /tmp (no .livespec.jsonc)
    result = _run_guard(stdin=stdin, cwd=Path("/tmp"))
    _assert_pass(result=result)


def test_deny_apply_patch_adding_file_under_codex_memories(tmp_path: Path) -> None:
    """apply_patch whose V4A patch ADDS a file under ~/.codex/memories/ → deny.

    apply_patch is Codex's primary file-edit tool; its target file paths live in
    the patch body as `*** Add/Update/Delete File: <path>` markers (the field
    carrying the patch text is matched tolerantly, so the exact tool_input key
    does not matter).
    """
    project = _governed_project(tmp_path=tmp_path)
    target = str(_MEMORIES_PATH / "learned.md")
    patch = (
        "*** Begin Patch\n"
        f"*** Add File: {target}\n"
        "+durable guidance an agent tried to persist\n"
        "*** End Patch\n"
    )
    stdin = _write_input(tool_name="apply_patch", tool_input={"input": patch})
    result = _run_guard(stdin=stdin, project_dir=str(project))
    payload = _assert_deny(result=result)
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert isinstance(reason, str)
    assert "capture-work-item" in reason
    assert "AGENTS.md" in reason


def test_deny_apply_patch_updating_file_under_codex_memories(tmp_path: Path) -> None:
    """apply_patch whose V4A patch UPDATES a file under ~/.codex/memories/ → deny."""
    project = _governed_project(tmp_path=tmp_path)
    target = str(_MEMORIES_PATH / "durable" / "prefs.md")
    patch = "*** Begin Patch\n" f"*** Update File: {target}\n" "@@\n-old\n+new\n" "*** End Patch\n"
    stdin = _write_input(tool_name="apply_patch", tool_input={"input": patch})
    result = _run_guard(stdin=stdin, project_dir=str(project))
    _assert_deny(result=result)


def test_pass_apply_patch_with_no_memories_target(tmp_path: Path) -> None:
    """apply_patch whose patch targets only repo files (no memories path) → pass."""
    project = _governed_project(tmp_path=tmp_path)
    patch = (
        "*** Begin Patch\n" "*** Update File: src/main.py\n" "@@\n-old\n+new\n" "*** End Patch\n"
    )
    stdin = _write_input(tool_name="apply_patch", tool_input={"input": patch})
    result = _run_guard(stdin=stdin, project_dir=str(project))
    _assert_pass(result=result)


def test_pass_apply_patch_to_memories_when_not_governed(tmp_path: Path) -> None:
    """apply_patch targeting memories but project NOT governed → pass (fail-open gate)."""
    target = str(_MEMORIES_PATH / "x.md")
    patch = f"*** Begin Patch\n*** Add File: {target}\n+note\n*** End Patch\n"
    stdin = _write_input(tool_name="apply_patch", tool_input={"input": patch})
    result = _run_guard(stdin=stdin, project_dir=str(tmp_path))  # no .livespec.jsonc
    _assert_pass(result=result)


def test_deny_with_jsonc_comments_and_cwd_project_discovery(tmp_path: Path) -> None:
    """JSONC stripping handles comments/escaped strings; cwd discovery finds the project."""
    (tmp_path / ".livespec.jsonc").write_text(
        "{\n"
        "  // line comment\n"
        '  "template": "livespec",\n'
        '  "note": "escaped \\" quote",\n'
        "  /* block comment */\n"
        '  "implementation": { "plugin": "livespec-impl-jsonc" }\n'
        "}\n",
        encoding="utf-8",
    )
    stdin = _write_input(
        tool_name="Write",
        tool_input={"file_path": str(_MEMORIES_PATH / "jsonc.md"), "content": "note"},
    )
    result = _run_guard(stdin=stdin, cwd=tmp_path)
    payload = _assert_deny(result=result)
    assert "livespec-impl-jsonc" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_pass_non_mapping_payload() -> None:
    result = _run_guard(stdin="[]")
    _assert_pass(result=result)


def test_pass_non_mapping_tool_input() -> None:
    stdin = json.dumps({"tool_name": "Write", "tool_input": "not a mapping"})
    result = _run_guard(stdin=stdin)
    _assert_pass(result=result)


def test_pass_malformed_or_ungoverned_project_configs(tmp_path: Path) -> None:
    for name, text in {
        "array": "[]",
        "missing-implementation": "{}",
        "bad-implementation": '{"implementation": []}',
        "blank-plugin": '{"implementation": {"plugin": "  "}}',
    }.items():
        project = tmp_path / name
        project.mkdir()
        (project / ".livespec.jsonc").write_text(text, encoding="utf-8")
        stdin = _write_input(
            tool_name="Write",
            tool_input={"file_path": str(_MEMORIES_PATH / f"{name}.md"), "content": "note"},
        )
        result = _run_guard(stdin=stdin, project_dir=str(project))
        _assert_pass(result=result)


def test_apply_patch_target_extraction_scans_nested_strings() -> None:
    target = str(_MEMORIES_PATH / "nested.md")
    patch = f"*** Begin Patch\n*** Move to: {target}\n*** End Patch\n"
    paths = block_auto_memory._target_file_paths(
        payload={"tool_name": "apply_patch", "tool_input": {"items": [123, {"patch": patch}]}}
    )
    assert paths == [target]
