#!/usr/bin/env python3
"""
Railway (Result / IOResult) primitives for the plugin-shipped Codex hooks.

This module is a SIBLING of the hooks that use it, and that placement is the
point. The plugin's packaged root is `./livespec` (`.agents/plugins/marketplace.json`
`plugins[0].source.path`), so Codex copies `livespec/` and nothing above it into
its install cache. A hook that reaches OUTSIDE that subtree for an import — as
these hooks previously did, reconstructing a repo root via
`Path(__file__).resolve().parents[2]` and importing the repo-root `_vendor.returns`
shim — raises `ModuleNotFoundError` at module scope in the real install layout,
BEFORE `main()`'s fail-open try/except can run. The process then exits non-zero
and the hook fails OPEN: a dangerous command executes unblocked while the guard
looks installed and correctly wired.

So every shipped hook imports these types as a plain sibling
(`from _result import ...`), which resolves against the hooks directory Python
already places on `sys.path` when running a script — the same mechanism the
hooks' existing `from _footgun_shell import ...` relies on. There is no path
arithmetic anywhere in the shipped tree, and the hooks run under a bare
`python3` with no venv and no third-party packages.

The surface is the small subset of dry-python/returns these hooks actually use,
behavior-identical to the shim it replaces: `Success` / `Failure` carry a value
and expose `unwrap()` / `failure()`, each raising `RuntimeError` on the wrong
track. `IOResult` / `IOSuccess` / `IOFailure` are aliases of the same types,
naming the effectful boundary (stdin reads, subprocess probes, SQLite opens)
without a separate implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, NoReturn, TypeAlias, TypeVar

__all__: list[str] = [
    "Failure",
    "IOFailure",
    "IOResult",
    "IOSuccess",
    "Result",
    "Success",
]

_T = TypeVar("_T")
_E = TypeVar("_E")


@dataclass(frozen=True)
class Success(Generic[_T]):
    """Successful railway value."""

    _inner_value: _T

    def unwrap(self) -> _T:
        return self._inner_value

    def failure(self) -> NoReturn:
        raise RuntimeError("Success has no failure value")


@dataclass(frozen=True)
class Failure(Generic[_E]):
    """Failed railway value."""

    _inner_value: _E

    def unwrap(self) -> NoReturn:
        raise RuntimeError("Failure has no success value")

    def failure(self) -> _E:
        return self._inner_value


Result: TypeAlias = Success[_T] | Failure[_E]

# The effectful-boundary spelling. Identical types; the distinct names keep the
# call sites self-describing about which side of an I/O boundary they sit on.
IOResult: TypeAlias = Result[_T, _E]
IOSuccess = Success
IOFailure = Failure
