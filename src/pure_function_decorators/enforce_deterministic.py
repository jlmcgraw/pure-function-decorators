"""Decorator that ensures a callable produces deterministic outputs."""

from __future__ import annotations

import asyncio
import logging
import pickle
import threading
from functools import wraps
from typing import TYPE_CHECKING, Final, cast, overload

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
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


def _sync_wrapper[**P, T](fn: Callable[P, T], *, strict: bool) -> Callable[P, T]:
    """Wrap ``fn`` with deterministic-result enforcement for sync callables.

    Parameters
    ----------
    fn : Callable[P, T]
        The synchronous callable whose outputs should remain stable.

    Returns:
    -------
    Callable[P, T]
        A wrapped callable that caches results and raises on divergence.
    """
    cache: dict[bytes, T] = {}
    lock = threading.RLock()

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
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

    return wrapper


def _async_wrapper[**P, AwaitedT](
    fn: Callable[P, Awaitable[AwaitedT]], *, strict: bool
) -> Callable[P, Awaitable[AwaitedT]]:
    """Wrap ``fn`` with deterministic-result enforcement for async callables.

    Parameters
    ----------
    fn : Callable[P, Awaitable[AwaitedT]]
        The asynchronous callable whose awaited results must not vary.

    Returns:
    -------
    Callable[P, Awaitable[AwaitedT]]
        A wrapped coroutine function that caches and validates outcomes.
    """
    cache: dict[bytes, AwaitedT] = {}
    lock = asyncio.Lock()

    @wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AwaitedT:
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

    return wrapper


@overload
def enforce_deterministic[**P, T](fn: Callable[P, T]) -> Callable[P, T]: ...


@overload
def enforce_deterministic[**P, T](
    *, enabled: bool = True, strict: bool = True
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def enforce_deterministic[**P, T](
    fn: Callable[P, T] | None = None,
    *,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]] | Callable[P, T]:
    """Ensure the callable always returns the same value for identical inputs.

    Parameters
    ----------
    fn : Callable[P, T] | None, optional
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

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if not enabled:
            return func
        if asyncio.iscoroutinefunction(func):
            async_fn = cast("Callable[P, Awaitable[object]]", func)
            wrapped = _async_wrapper(async_fn, strict=strict)
            return cast("Callable[P, T]", wrapped)

        return _sync_wrapper(func, strict=strict)

    if fn is not None:
        return decorator(fn)
    return decorator
