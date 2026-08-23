"""Unit tests for `livespec/hooks/_footgun_primary_checkout.py`.

Covers the primary-checkout-edit detection extracted from the footgun guard
(livespec epic livespec-i5ebqd, file_lloc decomposition) DIRECTLY: write-target
extraction (`redirect_targets`) and the primary-checkout probe
(`is_primary_checkout`). The guard's subprocess suite exercises these
end-to-end; the decomposition moves them behind a public module API, so they
earn their own direct coverage.

`is_primary_checkout` shells out to real `git`; the fixtures build hermetic tmp
repos (no dependency on any real checkout on the host), so they behave
identically locally and in CI.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import _footgun_primary_checkout  # noqa: E402 — path-dependent import after sys.path insert.
from _result import Failure  # noqa: E402 — same path-dependent import.

_real_run = subprocess.run

__all__: list[str] = []


def _tokens(*, command: str) -> list[str]:
    return shlex.split(command, posix=True)


# --------------------------------------------------------------------------
# redirect_targets
# --------------------------------------------------------------------------


def test_redirect_targets_plain_redirection() -> None:
    cmd = "echo hi > /tmp/out.txt"
    assert _footgun_primary_checkout.redirect_targets(seg=cmd, tokens=_tokens(command=cmd)) == [
        "/tmp/out.txt"
    ]


def test_redirect_targets_tee_operands() -> None:
    # Only the `tee` segment's tokens are passed (the guard checks per-segment).
    assert _footgun_primary_checkout.redirect_targets(
        seg="tee a.txt b.txt", tokens=_tokens(command="tee a.txt b.txt")
    ) == ["a.txt", "b.txt"]


def test_redirect_targets_sed_in_place() -> None:
    # `sed -i` is over-broad by design: it captures every trailing non-option
    # token (the script `s/a/b/` AND the file operand) as candidate targets.
    # That is conservative — a non-path candidate never resolves to a primary
    # checkout — and the file operand IS captured, which is what matters.
    cmd = "sed -i s/a/b/ file.txt"
    result = _footgun_primary_checkout.redirect_targets(seg=cmd, tokens=_tokens(command=cmd))
    assert "file.txt" in result


def test_redirect_targets_dd_of_operand() -> None:
    cmd = "dd if=/dev/zero of=out.bin bs=1 count=1"
    assert _footgun_primary_checkout.redirect_targets(seg=cmd, tokens=_tokens(command=cmd)) == [
        "out.bin"
    ]


def test_redirect_targets_git_apply_is_cwd() -> None:
    cmd = "git apply patch.diff"
    assert _footgun_primary_checkout.redirect_targets(seg=cmd, tokens=_tokens(command=cmd)) == ["."]


def test_redirect_targets_ignores_fd_duplication() -> None:
    # `2>&1` is a file-descriptor duplication, NOT a file write target.
    cmd = "printf out 2>&1"
    assert _footgun_primary_checkout.redirect_targets(seg=cmd, tokens=_tokens(command=cmd)) == []


# --------------------------------------------------------------------------
# is_primary_checkout
# --------------------------------------------------------------------------


def _git_init(*, root: Path) -> Path:
    subprocess.run(
        ["git", "init", "--quiet", str(root)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return root


def _init_primary_checkout(*, root: Path) -> str:
    """git-init `root` and mark it as its OWN primary checkout; return its toplevel."""
    _ = _git_init(root=root)
    toplevel = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    _ = subprocess.run(
        ["git", "-C", str(root), "config", "livespec.primaryPath", toplevel],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return toplevel


def test_is_primary_checkout_true_when_primary_path_matches(tmp_path: Path) -> None:
    root = _git_init(root=tmp_path / "primary")
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
    assert _footgun_primary_checkout.is_primary_checkout(path=toplevel) is True


def test_is_primary_checkout_false_without_primary_path(tmp_path: Path) -> None:
    root = _git_init(root=tmp_path / "plain-repo")
    assert _footgun_primary_checkout.is_primary_checkout(path=str(root)) is False


def test_is_primary_checkout_false_for_non_repo(tmp_path: Path) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    assert _footgun_primary_checkout.is_primary_checkout(path=str(plain)) is False


@pytest.mark.parametrize(
    "probe_error",
    [
        OSError("git launch failed"),
        subprocess.SubprocessError("git probe timed out"),
    ],
)
def test_is_primary_checkout_fails_open_without_caching_the_probe_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, probe_error: Exception
) -> None:
    """A failed probe fails OPEN at the boundary and is NOT remembered as an answer.

    ⛔ THE DEFECT THIS PINS. The `except` arm used to write
    `_PRIMARY_CHECKOUT_CACHE[real] = False` BEFORE returning `Failure`, so the
    NEXT call for the same path hit the cache and returned `Success(False)` — a
    transient probe failure laundered into a definitive negative that no consumer
    could tell from a real one. The consumer is the guard that refuses direct
    edits at a primary checkout, so one failed probe disarmed it for the rest of
    the process, permanently, rather than being retried.

    ⚠️ The fail-OPEN itself is contract-sanctioned (a hook must never wedge the
    agent) and is deliberately preserved: the boundary still answers False. What
    is removed is collapsing the failure TWO LEVELS BELOW that boundary and then
    CACHING it, which is precisely what the sanctioned fail-open assumes cannot
    happen.
    """
    real = str(tmp_path.resolve())
    _footgun_primary_checkout._PRIMARY_CHECKOUT_CACHE.clear()

    def fail_probe(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise probe_error

    monkeypatch.setattr(_footgun_primary_checkout.subprocess, "run", fail_probe)

    # The boundary still fails open — a hook must never wedge the agent.
    assert _footgun_primary_checkout.is_primary_checkout(path=str(tmp_path)) is False
    # ...but the failure is NOT recorded as though it were an answer.
    assert real not in _footgun_primary_checkout._PRIMARY_CHECKOUT_CACHE
    # ...and the private seam keeps reporting the failure instead of laundering it.
    assert isinstance(
        _footgun_primary_checkout._is_primary_checkout_result(path=str(tmp_path)),
        Failure,
    )


@pytest.mark.parametrize(
    "probe_error",
    [
        OSError("git launch failed"),
        subprocess.SubprocessError("git probe timed out"),
    ],
)
def test_probe_failure_does_not_poison_a_later_successful_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, probe_error: Exception
) -> None:
    """A recovered probe gives the TRUTHFUL answer, not the cached failure.

    ▶️ This is the half that makes the defect consequential rather than untidy.
    With the failure cached, the first transient error fixed the answer at False
    for the life of the process — so a repo that IS a primary checkout kept its
    guard disarmed long after git started working again.
    """
    toplevel = _init_primary_checkout(root=tmp_path / "primary")
    _footgun_primary_checkout._PRIMARY_CHECKOUT_CACHE.clear()

    failing = [True]

    def flaky(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if failing[0]:
            raise probe_error
        return _real_run(*args, **kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType]

    monkeypatch.setattr(_footgun_primary_checkout.subprocess, "run", flaky)
    assert _footgun_primary_checkout.is_primary_checkout(path=toplevel) is False

    failing[0] = False
    assert _footgun_primary_checkout.is_primary_checkout(path=toplevel) is True


def test_is_primary_checkout_propagates_unexpected_probe_bug(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _footgun_primary_checkout._PRIMARY_CHECKOUT_CACHE.clear()

    def bug(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise AttributeError("unexpected probe bug")

    monkeypatch.setattr(_footgun_primary_checkout.subprocess, "run", bug)

    with pytest.raises(AttributeError, match="unexpected probe bug"):
        _footgun_primary_checkout.is_primary_checkout(path=str(tmp_path))
