"""Decorator that ensures a callable produces deterministic outputs."""

from __future__ import annotations

import pickle
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
else:  # pragma: no cover
    import collections.abc as _abc

    Callable = _abc.Callable

_P = ParamSpec("_P")
_T = TypeVar("_T")


def enforce_deterministic(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Raise ``ValueError`` if ``fn`` returns different results for the same inputs."""
    cache: dict[bytes, _T] = {}

    @wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        key = pickle.dumps((args, kwargs))
        result = fn(*args, **kwargs)
        if key in cache and cache[key] != result:
            raise ValueError("Non-deterministic output detected")
        cache[key] = result
        return result

    return wrapper
