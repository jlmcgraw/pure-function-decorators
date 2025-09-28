"""Decorator that ensures a callable produces deterministic outputs."""

from __future__ import annotations

import asyncio
import logging
import pickle
import threading
from functools import wraps
from typing import Awaitable, Callable, Final, ParamSpec, TypeVar, cast, overload

_P = ParamSpec("_P")
_T = TypeVar("_T")
_AwaitedT = TypeVar("_AwaitedT")
_SyncFunc = TypeVar("_SyncFunc", bound=Callable[_P, _T])
_AsyncFunc = TypeVar(
    "_AsyncFunc", bound=Callable[_P, Awaitable[_AwaitedT]]
)
_MISSING: Final = object()

_LOGGER = logging.getLogger(__name__)


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

    Returns:
    -------
    bytes
        A pickle representation that can be used as a dictionary key.
    """
    return pickle.dumps((args, kwargs))


def _sync_wrapper(fn: _SyncFunc, *, strict: bool) -> _SyncFunc:
    """Wrap ``fn`` with deterministic-result enforcement for sync callables.

    Parameters
    ----------
    fn : Callable[_P, _T]
        The synchronous callable whose outputs should remain stable.

    Returns:
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
                message = "Non-deterministic output detected"
                if strict:
                    raise ValueError(message)
                _LOGGER.warning(message)
                with lock:
                    cache[key] = result
                return result
            return result
        with lock:
            current = cache.get(key, _MISSING)
            if current is not _MISSING and current != result:
                message = "Non-deterministic output detected"
                if strict:
                    raise ValueError(message)
                _LOGGER.warning(message)
                cache[key] = result
                return result
            cache[key] = result
        return result

    return cast(_SyncFunc, wrapper)


def _async_wrapper(fn: _AsyncFunc, *, strict: bool) -> _AsyncFunc:
    """Wrap ``fn`` with deterministic-result enforcement for async callables.

    Parameters
    ----------
    fn : Callable[_P, Awaitable[_AwaitedT]]
        The asynchronous callable whose awaited results must not vary.

    Returns:
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
                message = "Non-deterministic output detected"
                if strict:
                    raise ValueError(message)
                _LOGGER.warning(message)
                async with lock:
                    cache[key] = result
                return result
            return result
        async with lock:
            current = cache.get(key, _MISSING)
            if current is not _MISSING and current != result:
                message = "Non-deterministic output detected"
                if strict:
                    raise ValueError(message)
                _LOGGER.warning(message)
                cache[key] = result
                return result
            cache[key] = result
        return result

    return cast(_AsyncFunc, wrapper)


_DecoratedFunc = TypeVar("_DecoratedFunc", bound=Callable[_P, _T])


@overload
def enforce_deterministic(fn: _DecoratedFunc) -> _DecoratedFunc: ...


@overload
def enforce_deterministic(
    *, enabled: bool = True, strict: bool = True
) -> Callable[[_DecoratedFunc], _DecoratedFunc]: ...


def enforce_deterministic(
    fn: _DecoratedFunc | None = None,
    *,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[[_DecoratedFunc], _DecoratedFunc] | _DecoratedFunc:
    """Ensure the callable always returns the same value for identical inputs.

    Parameters
    ----------
    fn : Callable[_P, _T] | None, optional
        The function to wrap. When omitted, the decorator is returned for
        deferred application.
    enabled : bool, optional
        If ``False`` skip decorating and return ``fn`` unchanged.
    strict : bool, optional
        When ``False`` log warnings about non-deterministic behaviour instead of
        raising ``ValueError``.

    Returns:
    -------
    Callable
        Either the decorated function or a decorator awaiting a function,
        depending on whether ``fn`` was provided.
    """

    def decorator(func: _DecoratedFunc) -> _DecoratedFunc:
        if not enabled:
            return func
        if asyncio.iscoroutinefunction(func):
            async_fn = cast("Callable[_P, Awaitable[object]]", func)
            wrapped = cast(
                "Callable[_P, Awaitable[object]]",
                _async_wrapper(async_fn, strict=strict),
            )
            return cast(_DecoratedFunc, wrapped)

        return cast(_DecoratedFunc, _sync_wrapper(func, strict=strict))

    if fn is not None:
        return decorator(fn)
    return decorator
