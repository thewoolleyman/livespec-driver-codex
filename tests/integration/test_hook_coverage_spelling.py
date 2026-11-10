"""Witness for the hook coverage gate's pytest coverage spelling.

Covers SPECIFICATION/scenarios.md "the hook coverage gate combines under any
pytest coverage spelling": a throwaway project carrying this repository's REAL
`[tool.pytest.ini_options]` and `[tool.coverage.*]` tables runs pytest with
`--cov` and no `--cov-config`, over a hook test that starts a subprocess whose
working directory has no pyproject.toml in view. The run must end with pytest's
own exit status and print a coverage report instead of failing to combine
statement data with branch data.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TABLES = (
    "[tool.pytest.ini_options]",
    "[tool.coverage.run]",
    "[tool.coverage.report]",
)
_HOOK = "livespec_footgun_guard"

_HOOK_SOURCE = """\
def decide(*, blocked: bool) -> str:
    if blocked:
        return "deny"
    return "allow"
"""

_HOOK_TEST = f"""\
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "livespec" / "hooks"
CHILD = "import sys; sys.path.insert(0, sys.argv[1]); import {_HOOK}; {_HOOK}.decide(blocked=True)"


def test_hook_in_process_and_in_a_subprocess_outside_the_project(tmp_path):
    sys.path.insert(0, str(HOOKS))
    import {_HOOK}

    assert {_HOOK}.decide(blocked=True) == "deny"
    assert {_HOOK}.decide(blocked=False) == "allow"
    subprocess.run([sys.executable, "-c", CHILD, str(HOOKS)], cwd=tmp_path, check=True)
"""


def _real_table(*, pyproject: str, header: str) -> str:
    start = pyproject.index(header)
    following = re.search(r"^\[", pyproject[start + len(header) :], flags=re.MULTILINE)
    end = len(pyproject) if following is None else start + len(header) + following.start()
    return pyproject[start:end]


def _project(*, root: Path) -> Path:
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = root / "project"
    (project / "livespec" / "hooks").mkdir(parents=True)
    (project / "tests" / "hooks").mkdir(parents=True)
    tables = [_real_table(pyproject=pyproject, header=header) for header in _TABLES]
    (project / "pyproject.toml").write_text("\n".join(tables), encoding="utf-8")
    (project / "livespec" / "hooks" / f"{_HOOK}.py").write_text(_HOOK_SOURCE, encoding="utf-8")
    (project / "tests" / "hooks" / "test_hook.py").write_text(_HOOK_TEST, encoding="utf-8")
    return project


def _pytest(*, project: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_", "PYTEST_"))
    }
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args, "tests/hooks"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_bare_cov_run_combines_and_reports_coverage(tmp_path: Path) -> None:
    done = _pytest(project=_project(root=tmp_path), args=["--cov=livespec/hooks"])
    output = done.stdout + done.stderr
    assert "Can't combine statement coverage data with branch data" not in output
    assert "INTERNALERROR" not in output
    assert done.returncode == 0, output
    assert f"livespec/hooks/{_HOOK}.py" in done.stdout
    assert "TOTAL" in done.stdout


def test_run_without_cov_collects_and_runs_the_same_tests(tmp_path: Path) -> None:
    done = _pytest(project=_project(root=tmp_path), args=[])
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 passed" in done.stdout
    assert "TOTAL" not in done.stdout
