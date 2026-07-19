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
]


def _pyproject() -> dict[str, object]:
    return tomli.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_dry_python_returns_is_vendored_under_repo_vendor_tree() -> None:
    vendor_root = _REPO_ROOT / "_vendor" / "returns"

    assert (vendor_root / "__init__.py").is_file()
    assert (vendor_root / "result.py").is_file()
    assert (vendor_root / "io.py").is_file()


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
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("_vendor.returns")
            for node in ast.walk(tree)
        )
        constructs_result = any(
            isinstance(node, ast.Name)
            and node.id in {"Failure", "IOFailure", "IOSuccess", "Success"}
            for node in ast.walk(tree)
        )

        assert imports_returns, f"{hook_file.relative_to(_REPO_ROOT)} must import vendored returns"
        assert (
            constructs_result
        ), f"{hook_file.relative_to(_REPO_ROOT)} must construct railway values"
