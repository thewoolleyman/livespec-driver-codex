"""Live Codex TUI `/skills` picker acceptance.

This is the top-of-pyramid guard for the human path that `codex debug
prompt-input` cannot exercise: start the actual Codex TUI, open `/skills`,
choose "List skills", search for the short skill name, and require the picker
to render the plugin-qualified skill row.

Skip-vs-fail (work-item livespec-mjnv): the acceptance distinguishes "codex is
unavailable / unusable in THIS environment" from "the skill genuinely did not
resolve". codex absent, the TUI exiting mid-wait, or a timeout in any bring-up
phase (startup, `/skills` menu, picker open) → `pytest.skip` (the live smoke
cannot run here; CI runs it where codex is present and authenticated). Only a
timeout in the FINAL skill-row render — the picker is open and searched but the
plugin-qualified row never appears — is a genuine FAIL (the cross-harness
plugin-resolution Conformance concern's ob-4ts class). This is the per-harness
realization of the same skip-vs-fail decision the dev-tooling
`check-plugin-resolution` Verifier applies; codex's genuine live resolution
smoke is delegated to THIS check.
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import termios
import time
import tty
from collections.abc import Callable
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PICKER_QUERY = "orchestrate"
_EXPECTED_SKILL = "orchestrate"
_EXPECTED_PLUGIN = "livespec-orchestrator-beads-fabro"
_FOREGROUND_QUERY = "\x1b]10;?\x1b\\"
_BACKGROUND_QUERY = "\x1b]11;?\x1b\\"
_FOREGROUND_RESPONSE = "\x1b]10;rgb:ffff/ffff/ffff\x1b\\"
_BACKGROUND_RESPONSE = "\x1b]11;rgb:0000/0000/0000\x1b\\"
_TERMINAL_RESPONSES = _FOREGROUND_RESPONSE + _BACKGROUND_RESPONSE
_CODEX_STARTUP_TIMEOUT_SECONDS = 120
_GIT_HOOK_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def _plain(*, text: str) -> str:
    """Strip terminal control sequences enough for substring assertions."""
    return _ANSI_RE.sub("", text).replace("\r", "\n")


def _squashed(*, text: str) -> str:
    """Normalize TUI text whose inline mode may omit visible spaces."""
    return re.sub(r"\s+", "", text).lower()


def _has_main_prompt(*, plain: str) -> bool:
    squashed = _squashed(text=plain)
    return "model:" in squashed and "/modeltochange" in squashed


def _has_trust_prompt(*, plain: str) -> bool:
    return "doyoutrust" in _squashed(text=plain)


def _prepare_pty(*, slave_fd: int) -> None:
    """Give the spawned TUI a realistic terminal shape and input mode."""
    tty.setraw(slave_fd)
    winsize = struct.pack("HHHH", 40, 120, 0, 0)
    termios.tcflush(slave_fd, termios.TCIOFLUSH)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)


def _read_until(
    *,
    fd: int,
    seen: str,
    predicate: Callable[[str], bool],
    timeout_seconds: float,
    unavailable_on_timeout: bool,
) -> str:
    """Read from the PTY until `predicate(plain_text)` is true.

    `unavailable_on_timeout` folds in work-item livespec-mjnv: it distinguishes
    "codex is unavailable / unusable in this environment" (a SKIP — the smoke
    cannot run here) from "the skill genuinely did not resolve" (a FAIL). The
    bring-up phases (startup, `/skills` menu, picker open) pass `True`: a timeout
    there means codex never reached a usable picker (e.g. unauthenticated, no
    model configured, broken TUI), so the acceptance SKIPs rather than failing.
    Only the final skill-row render passes `False`: once the picker is open and
    searched, a timeout means the skill row did NOT resolve — a genuine FAIL (the
    ob-4ts class). A mid-wait `OSError` (the TUI exited) is always treated as
    unavailable (a SKIP): a crashed codex cannot prove non-resolution.
    """
    deadline = time.monotonic() + timeout_seconds
    current = seen
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        readable, _, _ = select.select([fd], [], [], min(0.25, remaining))
        if not readable:
            continue
        try:
            chunk = os.read(fd, 8192).decode("utf-8", errors="replace")
        except OSError:
            tail = _plain(text=current)[-3000:]
            pytest.skip(f"Codex TUI exited mid-wait; treating codex as unavailable.\n{tail}")
        current += chunk
        if _FOREGROUND_QUERY in chunk:
            _send(fd=fd, text=_FOREGROUND_RESPONSE)
        if _BACKGROUND_QUERY in chunk:
            _send(fd=fd, text=_BACKGROUND_RESPONSE)
        if predicate(_plain(text=current)):
            return current
    tail = _plain(text=current)[-3000:]
    if unavailable_on_timeout:
        pytest.skip(
            f"Timed out reaching a usable Codex picker; treating codex as unavailable.\n{tail}"
        )
    raise AssertionError(
        f"Codex picker opened but the expected skill row did not resolve. Last output:\n{tail}"
    )


def _send(*, fd: int, text: str) -> None:
    os.write(fd, text.encode("utf-8"))


def _await_codex_prompt(*, fd: int, transcript: str) -> str:
    current = _read_until(
        fd=fd,
        seen=transcript,
        predicate=lambda plain: _has_main_prompt(plain=plain) or _has_trust_prompt(plain=plain),
        timeout_seconds=_CODEX_STARTUP_TIMEOUT_SECONDS,
        unavailable_on_timeout=True,
    )
    if not _has_trust_prompt(plain=_plain(text=current)):
        return current
    _send(fd=fd, text="\r")
    return _read_until(
        fd=fd,
        seen=current,
        predicate=lambda plain: _has_main_prompt(plain=plain),
        timeout_seconds=_CODEX_STARTUP_TIMEOUT_SECONDS,
        unavailable_on_timeout=True,
    )


def _stop_codex(*, proc: subprocess.Popen[bytes], fd: int) -> None:
    """Exit the spawned TUI; escalate only if it ignores normal input."""
    if proc.poll() is None:
        try:
            _send(fd=fd, text="\x03")
            _send(fd=fd, text="/quit\r")
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    os.close(fd)


@pytest.mark.real_only
def test_skills_picker_finds_orchestrate_by_short_name() -> None:
    """The human `/skills` picker finds `orchestrate` under the beads plugin."""
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI not available; skipping the live /skills picker acceptance")

    master_fd, slave_fd = pty.openpty()
    _prepare_pty(slave_fd=slave_fd)
    env = os.environ.copy()
    env["TERM"] = env.get("TERM", "xterm-256color")
    env["NO_COLOR"] = "1"
    env.pop("CODEX_HOME", None)
    for name in _GIT_HOOK_ENV_VARS:
        env.pop(name, None)
    proc = subprocess.Popen(
        [codex, "--no-alt-screen", "-C", str(_REPO_ROOT)],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        close_fds=True,
    )
    os.close(slave_fd)
    _send(fd=master_fd, text=_TERMINAL_RESPONSES)
    transcript = ""
    try:
        transcript = _await_codex_prompt(fd=master_fd, transcript=transcript)
        _send(fd=master_fd, text="/skills\r")
        transcript = _read_until(
            fd=master_fd,
            seen=transcript,
            predicate=lambda plain: "listskills" in _squashed(text=plain)
            and "enable/disableskills" in _squashed(text=plain),
            timeout_seconds=15,
            unavailable_on_timeout=True,
        )
        _send(fd=master_fd, text="\r")
        transcript = _read_until(
            fd=master_fd,
            seen=transcript,
            predicate=lambda plain: "Skills" in plain or "Search" in plain,
            timeout_seconds=15,
            unavailable_on_timeout=True,
        )
        _send(fd=master_fd, text=_PICKER_QUERY)
        transcript = _read_until(
            fd=master_fd,
            seen=transcript,
            predicate=lambda plain: all(
                expected in plain for expected in (_EXPECTED_SKILL, _EXPECTED_PLUGIN, "Skill")
            ),
            timeout_seconds=15,
            unavailable_on_timeout=False,
        )
    finally:
        _stop_codex(proc=proc, fd=master_fd)

    plain = _plain(text=transcript)
    assert _EXPECTED_SKILL in plain
    assert _EXPECTED_PLUGIN in plain
    assert "Skill" in plain
