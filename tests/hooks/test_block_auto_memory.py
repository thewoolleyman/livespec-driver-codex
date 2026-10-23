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
- DENY, same reason: a Write / Edit / apply_patch into the Claude Code
  auto-memory layout (`~/.claude/projects/<slug>/memory/*.md`), and a Bash
  command that writes into either memory directory by redirection, a
  here-document, `tee`, `sed -i`, `cp`, `mv`, or an inline `python3 -c` write
  (work item livespec-driver-codex-qi5gkw; livespec core contracts.md v225).
- PASS (empty stdout, exit 0): non-memories target path; non-governed project;
  a Bash command that only reads a memory directory or removes a note with
  `rm`; no file_path in input; apply_patch with no memories path in patch
  content; empty or non-JSON stdin.
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

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GUARD_SCRIPT = _REPO_ROOT / "livespec" / "hooks" / "block_auto_memory.py"
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import block_auto_memory  # noqa: E402 — path-dependent hook import.

_MEMORIES_PATH = Path.home() / ".codex" / "memories"
_CLAUDE_MEMORY_PATH = Path.home() / ".claude" / "projects" / "-data-projects-demo" / "memory"

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


def test_pass_bash_read_of_memories_path(tmp_path: Path) -> None:
    """A Bash command that only reads a memory file → pass."""
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


def test_main_fails_open_when_decision_raises(monkeypatch, capsys) -> None:
    def explode():
        raise RuntimeError("boom")

    monkeypatch.setattr(block_auto_memory, "_decision", explode)

    assert block_auto_memory.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# (label, command) — DATA ONLY, fed to the guard's stdin, never executed.
_CODEX_SHELL_WRITES = [
    ("redirect", f"echo note > {_MEMORIES_PATH}/a.md"),
    ("append-tilde", "echo note >> ~/.codex/memories/a.md"),
    ("redirect-home-var", 'printf x > "$HOME/.codex/memories/a.md"'),
    ("tee", f"echo note | tee -a {_MEMORIES_PATH}/a.md"),
    ("sed-in-place", f"sed -i 's/a/b/' {_MEMORIES_PATH}/a.md"),
    ("cp", f"cp /tmp/n.md {_MEMORIES_PATH}/n.md"),
    ("mv", f"mv /tmp/n.md {_MEMORIES_PATH}/"),
    ("heredoc", f"cat > {_MEMORIES_PATH}/h.md <<'EOF'\nlearned a thing\nEOF"),
    # `>|` is bash's CLOBBER redirect, not a pipe. The segment splitter used to
    # cut at its `|`, so the memory path landed in a segment of its own and no
    # redirect target was ever read (work-item livespec-driver-codex-ydzrwk).
    ("clobber-redirect", f"echo note >| {_MEMORIES_PATH}/a.md"),
    ("clobber-append", f"echo note >>| {_MEMORIES_PATH}/a.md"),
    (
        "python3-c",
        f"python3 -c \"open('{_MEMORIES_PATH}/p.md', 'w').write('x')\"",
    ),
    # An interpreter reading its PROGRAM from a here-document. The body is
    # stripped before segmentation (it is stdin data, not shell), so it used to
    # reach no judge at all (work-item livespec-driver-codex-ydzrwk).
    (
        "heredoc-fed-python",
        f'python3 - <<EOF\nopen("{_MEMORIES_PATH}/h.md", "w").write("x")\nEOF',
    ),
    (
        "heredoc-fed-python-no-dash",
        f"python3 <<'PY'\nopen('{_MEMORIES_PATH}/h.md', 'a').write('x')\nPY",
    ),
    (
        "heredoc-fed-node",
        f'node <<EOF\nrequire("fs").writeFileSync("{_MEMORIES_PATH}/h.md", "x")\nEOF',
    ),
    (
        "heredoc-fed-perl",
        f'perl <<EOF\nopen(my $f, ">", "{_MEMORIES_PATH}/h.md")\nEOF',
    ),
    (
        "heredoc-fed-python-indent-stripped",
        f'python3 - <<-PY\n\topen("{_MEMORIES_PATH}/h.md", "w").write("x")\nPY',
    ),
    ("later-segment", f"cd /tmp && echo ok; echo note > {_MEMORIES_PATH}/a.md"),
    ("sh-c-payload", f"bash -c 'echo note > {_MEMORIES_PATH}/a.md'"),
    ("env-prefix", f"env A=1 tee {_MEMORIES_PATH}/a.md"),
]

_CLAUDE_SHELL_WRITES = [
    ("redirect", f"echo note > {_CLAUDE_MEMORY_PATH}/feedback.md"),
    ("cp-into-dir", f"cp /tmp/n.md {_CLAUDE_MEMORY_PATH}/"),
    ("tee", f"tee {_CLAUDE_MEMORY_PATH}/MEMORY.md < /tmp/index"),
]

_SHELL_READS_AND_REMOVALS = [
    ("cat", f"cat {_MEMORIES_PATH}/a.md"),
    ("grep", f"grep -rn rule {_CLAUDE_MEMORY_PATH}"),
    ("ls", "ls ~/.codex/memories/"),
    ("head", f"head -5 {_CLAUDE_MEMORY_PATH}/MEMORY.md"),
    ("find", f"find {_MEMORIES_PATH} -name '*.md'"),
    ("rm", f"rm {_CLAUDE_MEMORY_PATH}/stale.md {_MEMORIES_PATH}/old.md"),
    ("copy-out", f"cp {_MEMORIES_PATH}/a.md /tmp/a.md"),
    ("redirect-elsewhere", f"cat {_MEMORIES_PATH}/a.md > /tmp/a.md"),
]


def _bash_input(*, command: str) -> str:
    return _write_input(tool_name="Bash", tool_input={"command": command})


def _reason_for(*, stdin: str, project: Path) -> str:
    payload = _assert_deny(result=_run_guard(stdin=stdin, project_dir=str(project)))
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert isinstance(reason, str)
    return reason


@pytest.mark.parametrize(("label", "command"), _CODEX_SHELL_WRITES)
def test_deny_bash_write_into_codex_memories_with_the_file_tool_reason(
    tmp_path: Path, label: str, command: str
) -> None:
    """A shell write into ~/.codex/memories/ is refused with the intent-routing reason."""
    project = _governed_project(tmp_path=tmp_path)
    file_tool_reason = _reason_for(
        stdin=_write_input(
            tool_name="Write", tool_input={"file_path": str(_MEMORIES_PATH / "a.md")}
        ),
        project=project,
    )
    reason = _reason_for(stdin=_bash_input(command=command), project=project)
    assert reason == file_tool_reason, label
    assert "capture-work-item" in reason
    assert "/livespec:propose-change" in reason
    assert ".ai/<topic>.md" in reason


@pytest.mark.parametrize(("label", "command"), _CLAUDE_SHELL_WRITES)
def test_deny_bash_write_into_claude_memory_dir_with_the_same_reason(
    tmp_path: Path, label: str, command: str
) -> None:
    """A shell write into a Claude Code memory directory is refused, same reason."""
    project = _governed_project(tmp_path=tmp_path)
    codex_reason = _reason_for(
        stdin=_bash_input(command=f"echo x > {_MEMORIES_PATH}/a.md"), project=project
    )
    assert _reason_for(stdin=_bash_input(command=command), project=project) == codex_reason, label


@pytest.mark.parametrize("tool_name", ["Write", "Edit"])
def test_deny_file_tool_write_into_claude_memory_layout(tmp_path: Path, tool_name: str) -> None:
    project = _governed_project(tmp_path=tmp_path)
    stdin = _write_input(
        tool_name=tool_name, tool_input={"file_path": str(_CLAUDE_MEMORY_PATH / "user_role.md")}
    )
    _assert_deny(result=_run_guard(stdin=stdin, project_dir=str(project)))


def test_deny_apply_patch_into_claude_memory_layout(tmp_path: Path) -> None:
    project = _governed_project(tmp_path=tmp_path)
    patch = f"*** Begin Patch\n*** Add File: {_CLAUDE_MEMORY_PATH}/n.md\n+x\n*** End Patch\n"
    stdin = _write_input(tool_name="apply_patch", tool_input={"input": patch})
    _assert_deny(result=_run_guard(stdin=stdin, project_dir=str(project)))


@pytest.mark.parametrize(("label", "command"), _SHELL_READS_AND_REMOVALS)
def test_pass_bash_read_or_rm_of_a_memory_directory(
    tmp_path: Path, label: str, command: str
) -> None:
    """Reading a memory directory or removing a note with rm is never refused."""
    project = _governed_project(tmp_path=tmp_path)
    result = _run_guard(stdin=_bash_input(command=command), project_dir=str(project))
    assert result.returncode == 0, label
    assert result.stdout.strip() == "", f"{label}: expected pass-through, got {result.stdout!r}"


def test_pass_bash_memory_write_when_not_governed(tmp_path: Path) -> None:
    command = f"echo note > {_MEMORIES_PATH}/a.md"
    _assert_pass(result=_run_guard(stdin=_bash_input(command=command), project_dir=str(tmp_path)))


# Each here-document body must be judged against the segment that is FED it, not
# against any interpreter elsewhere in the command. Every case here carries a
# body that WOULD convict if bodies were pooled across segments, and none of
# them writes a memory file: the body naming a memory path is plain text `cat`
# writes to /tmp, and the body the interpreter actually runs is harmless.
#
# The last two are the shapes that make positional pooling wrong rather than
# merely sloppy. `same-terminator` gives both here-documents the name `EOF`, so
# matching on the terminator alone would hand BOTH bodies to the interpreter;
# only consuming a claimed body keeps each segment to its own. `quoted-body-
# introducer` hides `<<EOF` inside an `echo` argument, which the body scan still
# reads as an introducer — so a body is captured that no segment is fed, and the
# interpreter that follows would inherit it by position.
_HEREDOC_MISATTRIBUTION_PASSES = [
    (
        "text-body-first",
        f'cat > /tmp/draft.md <<\'EOF\'\nopen("{_MEMORIES_PATH}/x.md", "w").write("hi")\nEOF\n'
        'python3 - <<"PY"\nprint("hello")\nPY',
    ),
    (
        "text-body-second",
        'python3 - <<"PY"\nprint("hello")\nPY\n'
        f'cat > /tmp/draft.md <<\'EOF\'\nopen("{_MEMORIES_PATH}/x.md", "w").write("hi")\nEOF',
    ),
    (
        "same-terminator",
        f'cat > /tmp/draft.md <<\'EOF\'\nopen("{_MEMORIES_PATH}/x.md", "w").write("hi")\nEOF\n'
        'python3 - <<EOF\nprint("hello")\nEOF',
    ),
    (
        "quoted-body-introducer",
        f'echo "<<EOF"\nopen("{_MEMORIES_PATH}/x.md", "w").write("hi")\nEOF\n'
        'python3 - <<PY\nprint("hello")\nPY',
    ),
]


@pytest.mark.parametrize(("label", "command"), _HEREDOC_MISATTRIBUTION_PASSES)
def test_pass_heredoc_body_is_judged_against_the_segment_fed_it(
    tmp_path: Path, label: str, command: str
) -> None:
    """A body `cat` writes to /tmp never convicts an interpreter in another segment."""
    project = _governed_project(tmp_path=tmp_path)
    result = _run_guard(stdin=_bash_input(command=command), project_dir=str(project))
    assert result.returncode == 0, label
    assert result.stdout.strip() == "", f"{label}: expected pass-through, got {result.stdout!r}"


def test_pass_heredoc_whose_terminator_the_body_scan_cannot_read(tmp_path: Path) -> None:
    """A `<<$VAR` terminator is not a name this guard resolves, so no body is claimed."""
    project = _governed_project(tmp_path=tmp_path)
    command = f'python3 - <<$VAR\nopen("{_MEMORIES_PATH}/x.md", "w").write("hi")\n$VAR'
    _assert_pass(result=_run_guard(stdin=_bash_input(command=command), project_dir=str(project)))


def test_pass_interpreter_running_a_script_file_ignores_its_stdin(tmp_path: Path) -> None:
    """A here-document is DATA, not the program, when the interpreter names a script."""
    project = _governed_project(tmp_path=tmp_path)
    command = f'python3 render.py <<EOF\nopen("{_MEMORIES_PATH}/x.md", "w").write("hi")\nEOF'
    _assert_pass(result=_run_guard(stdin=_bash_input(command=command), project_dir=str(project)))


def test_subprocess_smoke_denies_bash_write_into_memories_when_governed(tmp_path: Path) -> None:
    """The shipped script judges a Bash payload over the real stdin/stdout protocol."""
    project = _governed_project(tmp_path=tmp_path)
    stdin = _bash_input(command=f"echo note | tee {_MEMORIES_PATH}/smoke.md")
    _assert_deny(result=_run_guard_subprocess(stdin=stdin, project_dir=str(project)))


def test_hooks_json_registers_the_guard_on_bash() -> None:
    """A body Codex never invokes for shell commands refuses nothing."""
    declared = json.loads((_HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))
    registered = {
        entry["matcher"]: [h["command"].rsplit("/", 1)[-1].rstrip('"') for h in entry["hooks"]]
        for entry in declared["hooks"]["PreToolUse"]
    }
    for matcher in ("Bash", "Write", "Edit", "apply_patch"):
        assert "block_auto_memory.py" in registered[matcher], matcher


@pytest.mark.parametrize("tool_input", [None, {}, {"command": ""}, {"command": ["echo"]}])
def test_pass_bash_payload_without_a_command_string(tmp_path: Path, tool_input: object) -> None:
    project = _governed_project(tmp_path=tmp_path)
    stdin = json.dumps({"tool_name": "Bash", "tool_input": tool_input})
    _assert_pass(result=_run_guard(stdin=stdin, project_dir=str(project)))
