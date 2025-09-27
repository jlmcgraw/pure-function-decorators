"""Decorator that ensures a callable produces deterministic outputs."""

from __future__ import annotations

import asyncio
import pickle
import threading
from collections.abc import Awaitable
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable
else:  # pragma: no cover
    import collections.abc as _abc

    Callable = _abc.Callable

_P = ParamSpec("_P")
_T = TypeVar("_T")
_MISSING = object()


def _pickle_args(
    args: _P.args, kwargs: _P.kwargs
) -> bytes:  # pragma: no cover - tiny helper
    return pickle.dumps((args, kwargs))


def _sync_wrapper(
    fn: Callable[_P, _T],
) -> Callable[_P, _T]:
    cache: dict[bytes, _T] = {}
    lock = threading.RLock()

    @wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        key = _pickle_args(args, kwargs)
        with lock:
            cached = cache.get(key, _MISSING)
        result = fn(*args, **kwargs)
        if cached is not _MISSING:
            if cached != result:
                raise ValueError("Non-deterministic output detected")
            return result
        with lock:
            current = cache.get(key, _MISSING)
            if current is not _MISSING and current != result:
                raise ValueError("Non-deterministic output detected")
            cache[key] = result
        return result

    return wrapper


def _async_wrapper(
    fn: Callable[_P, Awaitable[_T]],
) -> Callable[_P, Awaitable[_T]]:
    cache: dict[bytes, _T] = {}
    lock = asyncio.Lock()

    @wraps(fn)
    async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        key = _pickle_args(args, kwargs)
        async with lock:
            cached = cache.get(key, _MISSING)
        result = await fn(*args, **kwargs)
        if cached is not _MISSING:
            if cached != result:
                raise ValueError("Non-deterministic output detected")
            return result
        async with lock:
            current = cache.get(key, _MISSING)
            if current is not _MISSING and current != result:
                raise ValueError("Non-deterministic output detected")
            cache[key] = result
        return result

    return wrapper


@overload
def enforce_deterministic(
    fn: Callable[_P, _T],
) -> Callable[_P, _T]:  # pragma: no cover - typing overload
    ...


@overload
def enforce_deterministic(
    fn: Callable[_P, Awaitable[_T]],
) -> Callable[_P, Awaitable[_T]]:  # pragma: no cover - typing overload
    ...


def enforce_deterministic(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Raise ``ValueError`` if ``fn`` returns different results for the same inputs."""

    if asyncio.iscoroutinefunction(fn):
        return _async_wrapper(fn)

    return _sync_wrapper(fn)
