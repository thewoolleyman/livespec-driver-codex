"""Unit tests for `livespec/hooks/livespec_footgun_guard.py`.

The guard is exercised exactly as Codex runs it: as a subprocess, with
the PreToolUse hook input JSON on stdin
(`{"tool_name":"Bash","tool_input":{"command":"..."}}`) and the
`hookSpecificOutput.permissionDecision` payload read off stdout. Codex
consumes the Claude PreToolUse hook I/O format, so a `"deny"` decision
blocks the Bash call and an empty stdout + exit 0 lets it through.

Contract under test:

- DENY (token/segment based, the EXECUTED leading command of a
  segment): `git commit/push --no-verify`; a leading `LEFTHOOK=0|false`
  env-assignment; `git config core.bare <true>` (set form, both
  `core.bare true` and `core.bare=true`); a shell edit (redirect / tee
  / sed -i) writing INTO a livespec PRIMARY checkout (a repo whose
  `git config --get livespec.primaryPath` equals its own worktree
  root).
- PASS (empty stdout, exit 0): the dangerous strings as DATA (an
  `echo`, a `git config --get` read); a redirect to a non-primary
  path; a write to a non-primary repo/dir.
- FAIL-OPEN (empty stdout, exit 0): empty stdin, non-JSON stdin, a
  `tool_name` other than "Bash".

Follows the family Python rules (keyword-only args via the leading `*`
separator, `from __future__ import annotations`).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GUARD_SCRIPT = _REPO_ROOT / "livespec" / "hooks" / "livespec_footgun_guard.py"


def _hook_input(*, command: str, tool_name: str = "Bash") -> str:
    return json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})


def _run_guard(*, stdin: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(_GUARD_SCRIPT)],
        input=stdin,
        env={"PATH": os.environ["PATH"]},
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _assert_deny(*, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    """Assert the guard emitted a `deny` decision and exited 0; return the payload."""
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "expected a decision payload on stdout"
    payload = json.loads(result.stdout)
    hook_output = payload["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    return payload


def _assert_pass(*, result: subprocess.CompletedProcess[str]) -> None:
    """Assert the guard let the call through (empty stdout, exit 0)."""
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"expected silent pass-through; got {result.stdout!r}"


def _non_primary_git_repo(*, root: Path) -> Path:
    """Initialize a tmp git repo with NO livespec.primaryPath config.

    Such a repo is a valid git worktree but is NOT a primary checkout, so a
    write into it must pass.
    """
    subprocess.run(
        ["git", "init", "--quiet", str(root)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return root


def _primary_git_repo(*, root: Path) -> Path:
    """Initialize a tmp git repo and mark it as its OWN primary checkout.

    Sets `livespec.primaryPath` to the repo's own worktree root, so the guard
    recognizes a write INTO it as a primary-checkout edit. Hermetic — depends on
    NO real checkout on the host, so it behaves identically locally and in CI.
    Returns the repo's resolved worktree root (the write target's parent).
    """
    subprocess.run(
        ["git", "init", "--quiet", str(root)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    toplevel = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(root), "config", "livespec.primaryPath", toplevel],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return Path(toplevel)


# --------------------------------------------------------------------------
# (a) --no-verify on commit / push → deny
# --------------------------------------------------------------------------


def test_guard_script_exists() -> None:
    assert _GUARD_SCRIPT.is_file()


def test_denies_git_commit_no_verify() -> None:
    result = _run_guard(stdin=_hook_input(command="git commit --no-verify -m wip"))
    payload = _assert_deny(result=result)
    assert "--no-verify" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_git_push_no_verify() -> None:
    result = _run_guard(stdin=_hook_input(command="git push --no-verify origin HEAD"))
    _assert_deny(result=result)


def test_denies_mise_exec_wrapper_no_verify() -> None:
    # `_strip_leading_noise` must strip the `mise exec --` wrapper so the guard
    # inspects the real `git commit --no-verify` invocation underneath.
    result = _run_guard(stdin=_hook_input(command="mise exec -- git commit --no-verify -m wip"))
    _assert_deny(result=result)


def test_denies_no_verify_in_second_and_segment() -> None:
    # `_segments` splits on `&&`; the footgun is the SECOND segment, not the
    # leading benign `echo`.
    result = _run_guard(stdin=_hook_input(command="echo ok && git commit --no-verify"))
    _assert_deny(result=result)


# --------------------------------------------------------------------------
# (b) LEFTHOOK=0 / LEFTHOOK=false leading env-assignment → deny
# --------------------------------------------------------------------------


def test_denies_lefthook_zero_env_assignment() -> None:
    result = _run_guard(stdin=_hook_input(command="LEFTHOOK=0 git commit -m wip"))
    payload = _assert_deny(result=result)
    assert "LEFTHOOK" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_lefthook_false_env_assignment() -> None:
    result = _run_guard(stdin=_hook_input(command="LEFTHOOK=false git push origin HEAD"))
    _assert_deny(result=result)


# --------------------------------------------------------------------------
# (c) git config core.bare true / core.bare=true → deny
# --------------------------------------------------------------------------


def test_denies_git_config_core_bare_true_spaced() -> None:
    result = _run_guard(stdin=_hook_input(command="git config core.bare true"))
    payload = _assert_deny(result=result)
    assert "core.bare" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_git_config_core_bare_true_equals() -> None:
    result = _run_guard(stdin=_hook_input(command="git config core.bare=true"))
    _assert_deny(result=result)


# --------------------------------------------------------------------------
# (d) a write INTO a primary checkout → deny
# --------------------------------------------------------------------------


def test_passes_fd_duplication_redirections_in_primary_checkout(tmp_path: Path) -> None:
    primary = _primary_git_repo(root=tmp_path / "primary")
    result = _run_guard(
        stdin=_hook_input(command="printf err >&2; printf err 1>&2; printf out 2>&1"),
        cwd=primary,
    )
    _assert_pass(result=result)


def test_mixed_fd_duplication_and_redirect_classifies_only_file_target(tmp_path: Path) -> None:
    primary = _primary_git_repo(root=tmp_path / "primary")
    target = tmp_path / "outside-primary.txt"
    result = _run_guard(
        stdin=_hook_input(command=f"printf out 2>&1 > {target}"),
        cwd=primary,
    )
    _assert_pass(result=result)


def test_denies_redirect_into_primary_checkout(tmp_path: Path) -> None:
    primary = _primary_git_repo(root=tmp_path / "primary")
    target = primary / "scratch_probe.txt"
    result = _run_guard(stdin=_hook_input(command=f"echo hi > {target}"))
    payload = _assert_deny(result=result)
    assert "PRIMARY" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_tee_into_primary_checkout(tmp_path: Path) -> None:
    primary = _primary_git_repo(root=tmp_path / "primary")
    target = primary / "scratch_probe.txt"
    result = _run_guard(stdin=_hook_input(command=f"echo hi | tee {target}"))
    _assert_deny(result=result)


def test_denies_sed_in_place_into_primary_checkout(tmp_path: Path) -> None:
    primary = _primary_git_repo(root=tmp_path / "primary")
    target = primary / "scratch_probe.txt"
    result = _run_guard(stdin=_hook_input(command=f"sed -i s/a/b/ {target}"))
    _assert_deny(result=result)


def test_denies_dd_of_into_primary_checkout(tmp_path: Path) -> None:
    # `_redirect_targets` extracts the `dd of=<file>` operand as a write target;
    # into a primary checkout it must deny.
    primary = _primary_git_repo(root=tmp_path / "primary")
    target = primary / "scratch_probe.txt"
    result = _run_guard(stdin=_hook_input(command=f"dd if=/dev/zero of={target} bs=1 count=1"))
    payload = _assert_deny(result=result)
    assert "PRIMARY" in payload["hookSpecificOutput"]["permissionDecisionReason"]


# --------------------------------------------------------------------------
# benign passes — the dangerous strings as DATA, non-primary writes
# --------------------------------------------------------------------------


def test_passes_echo_of_no_verify_string() -> None:
    result = _run_guard(stdin=_hook_input(command='echo "never use --no-verify"'))
    _assert_pass(result=result)


def test_passes_git_config_get_core_bare_read() -> None:
    result = _run_guard(stdin=_hook_input(command="git config --get core.bare"))
    _assert_pass(result=result)


def test_passes_heredoc_body_carrying_no_verify_as_data() -> None:
    # `_strip_heredoc_bodies` drops the here-doc BODY (it is file data, not an
    # executed command), so a `--no-verify` string appearing ONLY inside the
    # body is not a footgun and must pass.
    command = "cat <<'EOF'\ngit commit --no-verify\nEOF"
    result = _run_guard(stdin=_hook_input(command=command))
    _assert_pass(result=result)


def test_passes_redirect_to_tmp(tmp_path: Path) -> None:
    target = tmp_path / "scratch.txt"
    result = _run_guard(stdin=_hook_input(command=f"echo hi > {target}"))
    _assert_pass(result=result)


def test_passes_write_to_non_primary_git_repo(tmp_path: Path) -> None:
    repo = _non_primary_git_repo(root=tmp_path / "repo")
    target = repo / "notes.txt"
    result = _run_guard(stdin=_hook_input(command=f"echo hi > {target}"))
    _assert_pass(result=result)


def test_passes_write_to_non_repo_directory(tmp_path: Path) -> None:
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    target = plain_dir / "out.txt"
    result = _run_guard(stdin=_hook_input(command=f"echo hi > {target}"))
    _assert_pass(result=result)


# --------------------------------------------------------------------------
# fail-open — empty / non-JSON stdin, non-Bash tool
# --------------------------------------------------------------------------


def test_fail_open_empty_stdin() -> None:
    result = _run_guard(stdin="")
    _assert_pass(result=result)


def test_fail_open_non_json_stdin() -> None:
    result = _run_guard(stdin="not json at all")
    _assert_pass(result=result)


def test_fail_open_non_bash_tool() -> None:
    result = _run_guard(stdin=_hook_input(command="git commit --no-verify", tool_name="Write"))
    _assert_pass(result=result)
