"""Static policy tests for the Driver hook railway adoption."""

from __future__ import annotations

import ast
from pathlib import Path

import tomli

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOK_FILES = [
    _REPO_ROOT / "livespec" / "hooks" / "block_auto_memory.py",
    _REPO_ROOT / "livespec" / "hooks" / "codex_background_memory_audit.py",
    _REPO_ROOT / "livespec" / "hooks" / "livespec_footgun_guard.py",
    _REPO_ROOT / "livespec" / "hooks" / "_footgun_primary_checkout.py",
    _REPO_ROOT / "livespec" / "hooks" / "_footgun_shell.py",
    _REPO_ROOT / "livespec" / "hooks" / "_footgun_tmux.py",
]


def _pyproject() -> dict[str, object]:
    return tomli.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_railway_types_live_inside_the_packaged_plugin_subtree() -> None:
    """The railway shim must ship WITH the hooks, not above them.

    Only `livespec/` is packaged, so a railway module anywhere else is absent
    at runtime and every hook importing it fails open.
    """
    assert (_REPO_ROOT / "livespec" / "hooks" / "_result.py").is_file()


def test_no_shipped_hook_reaches_outside_the_packaged_subtree() -> None:
    """Regression guard for the fail-open packaging defect.

    Reconstructing a repo root with `Path(__file__).resolve().parents[N]` and
    inserting it on `sys.path` works in the checkout and breaks in the install
    cache. No shipped hook may do it, and none may import the repo-root
    `_vendor` tree that arithmetic existed to reach.
    """
    for hook_file in _HOOK_FILES:
        source = hook_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        offender = hook_file.relative_to(_REPO_ROOT)

        reaches_out = any(
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "_vendor"
            for node in ast.walk(tree)
        )
        mutates_path = any(
            isinstance(node, ast.Attribute)
            and node.attr == "path"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
            for node in ast.walk(tree)
        )

        assert not reaches_out, f"{offender} imports the unpackaged _vendor tree"
        assert not mutates_path, f"{offender} manipulates sys.path at import time"


def test_linter_and_typechecker_policy_enable_ble_and_unused_call_results() -> None:
    config = _pyproject()
    ruff_lint = config["tool"]["ruff"]["lint"]  # type: ignore[index]
    pyright = config["tool"]["pyright"]  # type: ignore[index]

    assert "BLE" in ruff_lint["select"]
    assert pyright["reportUnusedCallResult"] == "error"


def test_hook_modules_import_and_use_returns_railway_types() -> None:
    for hook_file in _HOOK_FILES:
        tree = ast.parse(hook_file.read_text(encoding="utf-8"))
        imports_returns = any(
            isinstance(node, ast.ImportFrom) and node.module == "_result" for node in ast.walk(tree)
        )
        constructs_result = any(
            isinstance(node, ast.Name)
            and node.id in {"Failure", "IOFailure", "IOSuccess", "Success"}
            for node in ast.walk(tree)
        )

        assert (
            imports_returns
        ), f"{hook_file.relative_to(_REPO_ROOT)} must import the sibling railway shim"
        assert (
            constructs_result
        ), f"{hook_file.relative_to(_REPO_ROOT)} must construct railway values"
