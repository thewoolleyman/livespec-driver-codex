"""Small vendored IOResult surface compatible with dry-python/returns usage here."""

from __future__ import annotations

from typing import TypeAlias, TypeVar

from _vendor.returns.result import Failure, Result, Success

_T = TypeVar("_T")
_E = TypeVar("_E")

IOResult: TypeAlias = Result[_T, _E]
IOSuccess = Success
IOFailure = Failure

__all__ = ["IOFailure", "IOResult", "IOSuccess"]
