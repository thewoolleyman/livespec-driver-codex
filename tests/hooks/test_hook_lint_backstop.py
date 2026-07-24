"""Regression tests for the hook-tree Ruff backstop."""

from __future__ import annotations

import ast
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOKS_DIR = _REPO_ROOT / "livespec" / "hooks"


def _tree_for(*, rel_path: str) -> ast.Module:
    return ast.parse((_HOOKS_DIR / rel_path).read_text(encoding="utf-8"))


def test_footgun_guard_stdout_boundary_uses_explicit_write() -> None:
    tree = _tree_for(rel_path="livespec_footgun_guard.py")
    print_calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]
    assert print_calls == []
