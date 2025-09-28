"""Decorator that ensures a callable produces deterministic outputs."""

from __future__ import annotations

import asyncio
import pickle
import threading
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Final, ParamSpec, TypeVar, cast

_P = ParamSpec("_P")
_T = TypeVar("_T")
_AwaitedT = TypeVar("_AwaitedT")
_MISSING: Final = object()


def _pickle_args(
    *args: object, **kwargs: object
) -> bytes:  # pragma: no cover - tiny helper
    """Serialize positional and keyword arguments into a cache key.

    Parameters
    ----------
    *args : object
        Positional arguments supplied to the decorated callable.
    **kwargs : object
        Keyword arguments supplied to the decorated callable.

    Returns
    -------
    bytes
        A pickle representation that can be used as a dictionary key.
    """

    return pickle.dumps((args, kwargs))


def _sync_wrapper(
    fn: Callable[_P, _T],
) -> Callable[_P, _T]:
    """Wrap ``fn`` with deterministic-result enforcement for sync callables.

    Parameters
    ----------
    fn : Callable[_P, _T]
        The synchronous callable whose outputs should remain stable.

    Returns
    -------
    Callable[_P, _T]
        A wrapped callable that caches results and raises on divergence.
    """

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
    """Wrap ``fn`` with deterministic-result enforcement for async callables.

    Parameters
    ----------
    fn : Callable[_P, Awaitable[_AwaitedT]]
        The asynchronous callable whose awaited results must not vary.

    Returns
    -------
    Callable[_P, Awaitable[_AwaitedT]]
        A wrapped coroutine function that caches and validates outcomes.
    """

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
    """Ensure the callable always returns the same value for identical inputs.

    Parameters
    ----------
    fn : Callable[_P, _T]
        The synchronous or asynchronous callable to wrap.

    Returns
    -------
    Callable[_P, _T]
        A wrapper that caches results per argument signature and raises
        ``ValueError`` if a subsequent invocation produces a different
        outcome.
    """

    if asyncio.iscoroutinefunction(fn):
        async_fn = cast("Callable[_P, Awaitable[object]]", fn)
        wrapped: Callable[_P, Awaitable[object]] = _async_wrapper(async_fn)
        return cast("Callable[_P, _T]", wrapped)

    return _sync_wrapper(fn)
