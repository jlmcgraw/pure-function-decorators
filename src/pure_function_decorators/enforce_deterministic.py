"""Decorator that ensures a callable produces deterministic outputs."""

from __future__ import annotations

import asyncio
import pickle
import threading
from collections.abc import Awaitable
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
else:  # pragma: no cover
    import collections.abc as _abc

    Callable = _abc.Callable

_P = ParamSpec("_P")
_T = TypeVar("_T")
_AwaitedT = TypeVar("_AwaitedT")
_MISSING = object()


def _pickle_args(
    *args: object, **kwargs: object
) -> bytes:  # pragma: no cover - tiny helper
    return pickle.dumps((args, kwargs))


def _sync_wrapper(
    fn: Callable[_P, _T],
) -> Callable[_P, _T]:
    cache: dict[bytes, _T] = {}
    lock = threading.RLock()

    @wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        key = _pickle_args(*args, **kwargs)
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
    fn: Callable[_P, Awaitable[_AwaitedT]],
) -> Callable[_P, Awaitable[_AwaitedT]]:
    cache: dict[bytes, _AwaitedT] = {}
    lock = asyncio.Lock()

    @wraps(fn)
    async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _AwaitedT:
        key = _pickle_args(*args, **kwargs)
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


def enforce_deterministic(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Raise ``ValueError`` if ``fn`` returns different results for the same inputs."""
    if asyncio.iscoroutinefunction(fn):
        async_fn = cast(Callable[_P, Awaitable[object]], fn)
        wrapped: Callable[_P, Awaitable[object]] = _async_wrapper(async_fn)
        return cast(Callable[_P, _T], wrapped)

    return _sync_wrapper(fn)
