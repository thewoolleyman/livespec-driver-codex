from __future__ import annotations

import os
import subprocess
from pathlib import Path

from livespec_dev_tooling.checks import shell_quality


def _run(*, cwd: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_clean_shell_repo(*, repo: Path, justfile: str) -> None:
    scripts = repo / "scripts"
    scripts.mkdir()
    (scripts / "clean.sh").write_text(
        "#!/usr/bin/env bash\n" "set -euo pipefail\n" "printf '%s\\n' clean\n",
        encoding="utf-8",
    )
    (repo / "justfile").write_text(justfile, encoding="utf-8")
    _ = _run(cwd=repo, argv=["git", "init"])
    _ = _run(cwd=repo, argv=["git", "add", "scripts/clean.sh"])


def _shell_quality(
    *,
    repo: Path,
    monkeypatch,
    capsys,
) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    monkeypatch.chdir(repo)
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "environ", env)
        rc = shell_quality.main()
    captured = capsys.readouterr()
    return rc, captured.err


def test_shell_quality_accepts_clean_surface(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_clean_shell_repo(
        repo=tmp_path,
        justfile="check:\n    bash scripts/clean.sh\n",
    )

    rc, stderr = _shell_quality(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_shell_quality_rejects_just_interpolation(tmp_path: Path, monkeypatch, capsys) -> None:
    interpolation = "{{" + "args" + "}}"
    _write_clean_shell_repo(
        repo=tmp_path,
        justfile=f"check *args:\n    echo {interpolation}\n",
    )

    rc, stderr = _shell_quality(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1
    assert '"reason": "just-interpolation"' in stderr
