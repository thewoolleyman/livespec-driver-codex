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
def test_is_primary_checkout_fails_open_and_caches_false_for_expected_probe_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, probe_error: Exception
) -> None:
    real = str(tmp_path.resolve())
    _footgun_primary_checkout._PRIMARY_CHECKOUT_CACHE.clear()

    def fail_probe(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise probe_error

    monkeypatch.setattr(_footgun_primary_checkout.subprocess, "run", fail_probe)

    assert _footgun_primary_checkout.is_primary_checkout(path=str(tmp_path)) is False
    assert _footgun_primary_checkout._PRIMARY_CHECKOUT_CACHE[real] is False


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
