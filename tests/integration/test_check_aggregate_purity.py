"""Witnesses for the aggregate's purity-declaration admission gate."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGGREGATE = _REPO_ROOT / "dev-tooling" / "check-aggregate.sh"


def _write_executable(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_aggregate_refuses_an_undeclared_member_before_running_it(tmp_path: Path) -> None:
    """A missing declaration names the member and prevents its recipe from running."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    calls.touch()
    (tmp_path / "check-targets.txt").write_text("check-example\n", encoding="utf-8")
    _write_executable(
        path=bin_dir / "uv",
        body="""#!/usr/bin/env bash
printf 'uv %s\\n' \"$*\" >> \"$FAKE_LOG\"
case \"$*\" in
  *\"green_token undeclared\"*) printf 'check-example\\n'; exit 1 ;;
  *\"green_token write\"*) exit 0 ;;
esac
exit 99
""",
    )
    _write_executable(
        path=bin_dir / "just",
        body="""#!/usr/bin/env bash
printf 'just %s\\n' \"$*\" >> \"$FAKE_LOG\"
exit 0
""",
    )

    result = subprocess.run(
        ["bash", str(_AGGREGATE)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(calls),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "check-example" in result.stdout
    assert "check-purity-declarations" in result.stderr
    assert not any(call.startswith("just check-example") for call in calls.read_text().splitlines())
