"""Small vendored Result surface compatible with dry-python/returns usage here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, NoReturn, TypeAlias, TypeVar

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

__all__ = ["Failure", "Result", "Success"]
