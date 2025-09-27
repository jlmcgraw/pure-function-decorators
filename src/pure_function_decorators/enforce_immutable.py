"""Decorator that deep-copies inputs before invoking the wrapped callable."""

from __future__ import annotations

import copy
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
else:  # pragma: no cover
    import collections.abc as _abc

    Callable = _abc.Callable

_P = ParamSpec("_P")
_T = TypeVar("_T")


def enforce_immutable(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Invoke ``fn`` with deep-copied arguments to prevent caller mutations."""

    @wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        frozen_args = copy.deepcopy(args)
        frozen_kwargs = copy.deepcopy(kwargs)
        return fn(*frozen_args, **frozen_kwargs)

    return wrapper
