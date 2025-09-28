"""Heuristic decorator that blocks common side effects during a call."""

from __future__ import annotations

import asyncio
import atexit
import builtins
import concurrent.futures as futures
import datetime
import importlib
import inspect
import logging
import multiprocessing
import os
import random
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
import warnings
from contextlib import suppress
from functools import wraps
from collections.abc import Awaitable, Callable, Iterator, MutableMapping
from typing import (
    Final,
    NoReturn,
    Protocol,
    Self,
    TypeVar,
    cast,
    overload,
    override,
    runtime_checkable,
)

_LOGGER = logging.getLogger(__name__)


class _HybridRLock:
    """Lock usable as both sync and async context manager."""

    def __init__(self) -> None:
        """Initialize the underlying re-entrant lock."""
        self._lock: threading.RLock = threading.RLock()

    def __enter__(self) -> Self:
        """Acquire the lock for use in a synchronous ``with`` block.

        Returns:
        -------
        _HybridRLock
            The lock instance, matching the context manager protocol.
        """
        self._lock.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        """Release the lock on exit from a synchronous ``with`` block."""
        self._lock.release()

    async def __aenter__(self) -> Self:
        """Acquire the lock for use in an ``async with`` block.

        Returns:
        -------
        _HybridRLock
            The lock instance, matching the async context manager protocol.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._lock.acquire)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Release the lock on exit from an ``async with`` block."""
        self._lock.release()


_SIDE_EFFECT_LOCK: Final = _HybridRLock()


def _emit_warning(message: str) -> None:
    """Write warnings to the original stderr stream."""
    stderr = sys.__stderr__
    if stderr is None:  # pragma: no cover - depends on interpreter configuration
        _LOGGER.warning("%s", message)
        return

    try:
        stderr.write(f"{message}\n")
        stderr.flush()
    except Exception:  # pragma: no cover - defensive fallback
        _LOGGER.exception("Failed to write warning to stderr: %s", message)


def _trap(
    name: str,
    *,
    strict: bool,
    original: Callable[..., object] | None = None,
) -> Callable[..., object]:
    """Return a callable that reacts to blocked side-effect attempts.

    Parameters
    ----------
    name : str
        Human-readable description of the blocked operation.

    Returns:
    -------
    Callable[..., object]
        A function that raises ``RuntimeError`` or logs warnings based on
        ``strict`` whenever it is called.
    """

    def _handler(*args: object, **kwargs: object) -> object:
        message = f"Side effect blocked: {name}"
        if strict:
            raise RuntimeError(message)
        _emit_warning(message)
        if original is not None:
            return original(*args, **kwargs)
        return None

    return _handler


@runtime_checkable
class _SupportsWrite(Protocol):
    """Protocol for objects that expose a ``write`` method."""

    def write(self, *args: object, **kwargs: object) -> object: ...


@runtime_checkable
class _SupportsFlush(Protocol):
    """Protocol for objects that expose a ``flush`` method."""

    def flush(self) -> object: ...


class _TrapStdIO:
    """File-like object that reacts to writes to stdout/stderr."""

    def __init__(
        self,
        *,
        strict: bool,
        original: object | None = None,
    ) -> None:
        """Store behaviour configuration for stdio interception."""
        self._strict: bool
        self._original: object | None

        self._strict = strict
        self._original = original

    def write(self, *args: object, **kwargs: object) -> object | None:
        """Handle writes by raising or delegating with a warning."""
        message = "Side effect blocked: stdio write"
        if self._strict:
            raise RuntimeError(message)
        _emit_warning(message)
        original = self._original
        if original is not None and isinstance(original, _SupportsWrite):
            return original.write(*args, **kwargs)
        return None

    def flush(self) -> object | None:
        """Provide a harmless flush implementation for callers that expect one."""
        original = self._original
        if original is not None and isinstance(original, _SupportsFlush):
            return original.flush()
        return None

    def __getattr__(self, item: str) -> object:
        """Delegate attribute access to the wrapped stream when available."""
        if self._original is None:
            raise AttributeError(item)
        return getattr(self._original, item)


_T = TypeVar("_T")


class _TrapEnviron(MutableMapping[str, str]):
    """Proxy object that enforces side-effect policy for ``os.environ``."""

    def __init__(self, *, strict: bool, original: MutableMapping[str, str]) -> None:
        self._strict: bool
        self._original: MutableMapping[str, str]

        self._strict = strict
        self._original = original

    @override
    def __getitem__(self, key: str) -> str:
        message = "Side effect blocked: os.environ[] read"
        if self._strict:
            raise RuntimeError(message)
        _emit_warning(message)
        return self._original[key]

    @override
    def __setitem__(self, key: str, value: str) -> None:
        message = "Side effect blocked: os.environ[] write"
        if self._strict:
            raise RuntimeError(message)
        _emit_warning(message)
        self._original[key] = value

    @override
    def __delitem__(self, key: str) -> None:
        message = "Side effect blocked: os.environ del"
        if self._strict:
            raise RuntimeError(message)
        _emit_warning(message)
        del self._original[key]

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._original)

    @override
    def __len__(self) -> int:
        return len(self._original)

    @overload
    def get(self, key: str, default: None = None) -> str | None: ...

    @overload
    def get(self, key: str, default: str) -> str: ...

    @overload
    def get(self, key: str, default: _T) -> str | _T: ...

    @override
    def get(
        self, key: str, default: _T | None = None
    ) -> str | _T | None:  # pragma: no cover - passthrough
        message = "Side effect blocked: os.environ.get"
        if self._strict:
            raise RuntimeError(message)
        _emit_warning(message)
        if key in self._original:
            return self._original[key]
        return default


def _make_datetime_proxy(*, strict: bool) -> type[datetime.datetime]:
    """Create a ``datetime.datetime`` subclass that enforces policy."""
    if strict:

        class _TrapDateTime(datetime.datetime):
            @override
            @classmethod
            def now(cls, tz: datetime.tzinfo | None = None) -> NoReturn:
                raise RuntimeError("Side effect blocked: datetime.now")

            @override
            @classmethod
            def utcnow(cls) -> NoReturn:
                raise RuntimeError("Side effect blocked: datetime.utcnow")

            @override
            @classmethod
            def today(cls) -> NoReturn:
                raise RuntimeError("Side effect blocked: datetime.today")

        return _TrapDateTime

    class _WarnDateTime(datetime.datetime):
        @override
        @classmethod
        def now(cls, tz: datetime.tzinfo | None = None) -> _WarnDateTime:
            _emit_warning("Side effect blocked: datetime.now")
            return super().now(tz) if tz is not None else super().now()

        @override
        @classmethod
        def utcnow(cls) -> _WarnDateTime:
            _emit_warning("Side effect blocked: datetime.utcnow")
            return super().now(datetime.UTC)

        @override
        @classmethod
        def today(cls) -> _WarnDateTime:
            _emit_warning("Side effect blocked: datetime.today")
            return super().today()

    return _WarnDateTime


def _apply_patches(strict: bool) -> list[tuple[object, str, object]]:
    """Monkeypatch common side-effect primitives with trapping functions.

    Parameters
    ----------
    strict : bool
        When ``False`` original behaviour is preserved after emitting warnings.

    Returns:
    -------
    list[tuple[object, str, object]]
        Triples describing each patch so it can be undone later.
    """
    patches: list[tuple[object, str, object]] = []

    def patch_callable(obj: object, attr: str, name: str) -> None:
        original = getattr(obj, attr)
        replacement = _trap(
            name,
            strict=strict,
            original=None if strict else cast("Callable[..., object]", original),
        )
        setattr(obj, attr, replacement)
        patches.append((obj, attr, original))

    def patch_value(
        obj: object, attr: str, factory: Callable[[object], object]
    ) -> None:
        original = getattr(obj, attr)
        setattr(obj, attr, factory(original))
        patches.append((obj, attr, original))

    for func_obj, attr, name in (
        (builtins, "print", "print"),
        (builtins, "open", "open"),
        (random, "random", "random.random"),
        (random, "randint", "random.randint"),
        (random, "randrange", "random.randrange"),
        (random, "choice", "random.choice"),
        (random, "shuffle", "random.shuffle"),
        (secrets, "token_bytes", "secrets.token_bytes"),
        (secrets, "token_hex", "secrets.token_hex"),
        (secrets, "token_urlsafe", "secrets.token_urlsafe"),
        (os, "urandom", "os.urandom"),
        (uuid, "uuid4", "uuid.uuid4"),
        (time, "time", "time.time"),
        (time, "sleep", "time.sleep"),
        (time, "monotonic", "time.monotonic"),
        (time, "perf_counter", "time.perf_counter"),
        (os, "getenv", "os.getenv"),
        (os, "system", "os.system"),
        (os, "popen", "os.popen"),
        (os, "_exit", "os._exit"),
        (sys, "exit", "sys.exit"),
        (subprocess, "run", "subprocess.run"),
        (subprocess, "Popen", "subprocess.Popen"),
        (subprocess, "call", "subprocess.call"),
        (subprocess, "check_call", "subprocess.check_call"),
        (subprocess, "check_output", "subprocess.check_output"),
        (socket, "socket", "socket.socket"),
        (threading.Thread, "start", "threading.Thread.start"),
        (multiprocessing.Process, "start", "multiprocessing.Process.start"),
        (
            futures.ThreadPoolExecutor,
            "__init__",
            "ThreadPoolExecutor.__init__",
        ),
        (
            futures.ProcessPoolExecutor,
            "__init__",
            "ProcessPoolExecutor.__init__",
        ),
        (logging.Logger, "_log", "logging"),
        (warnings, "warn", "warnings.warn"),
        (atexit, "register", "atexit.register"),
    ):
        patch_callable(func_obj, attr, name)

    patch_value(
        datetime,
        "datetime",
        lambda _orig: _make_datetime_proxy(strict=strict),
    )

    patch_value(
        os,
        "environ",
        lambda original: _TrapEnviron(
            strict=strict,
            original=cast("MutableMapping[str, str]", original),
        ),
    )

    patch_value(
        sys,
        "stdout",
        lambda original: _TrapStdIO(strict=strict, original=original),
    )
    patch_value(
        sys,
        "stderr",
        lambda original: _TrapStdIO(strict=strict, original=original),
    )

    with suppress(Exception):
        sqlite3 = importlib.import_module("sqlite3")
        patch_callable(sqlite3, "connect", "sqlite3.connect")
    with suppress(Exception):
        psycopg2 = importlib.import_module("psycopg2")
        patch_callable(psycopg2, "connect", "psycopg2.connect")
    with suppress(Exception):
        mysql_connector = importlib.import_module("mysql.connector")
        patch_callable(mysql_connector, "connect", "mysql.connector.connect")

    with suppress(Exception):
        import http.client as http_client

        patch_callable(http_client, "HTTPConnection", "http.client.HTTPConnection")
        patch_callable(http_client, "HTTPSConnection", "http.client.HTTPSConnection")

    return patches


def _restore(patches: list[tuple[object, str, object]]) -> None:
    """Revert previously applied monkeypatches.

    Parameters
    ----------
    patches : list[tuple[object, str, object]]
        Patch descriptors returned by :func:`_apply_patches`.
    """
    for obj, attr, original in reversed(patches):
        setattr(obj, attr, original)


@overload
def forbid_side_effects[**P, T](
    fn: Callable[P, T], *, enabled: bool = True, strict: bool = True
) -> Callable[P, T]: ...


@overload
def forbid_side_effects[**P, T](
    *, enabled: bool = True, strict: bool = True
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def forbid_side_effects[**P, T](
    fn: Callable[P, T] | None = None,
    *,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]] | Callable[P, T]:
    """Reject attempts to perform common side effects while ``fn`` runs.

    Parameters
    ----------
    fn : Callable[P, T] | None, optional
        The synchronous or asynchronous callable to wrap.
    enabled : bool, optional
        If ``False`` skip decorating and return ``fn`` unchanged.
    strict : bool, optional
        When ``False`` warn about attempted side effects but allow the original
        call to proceed.

    Returns:
    -------
    Callable
        Either the decorated function or a decorator awaiting a function,
        depending on whether ``fn`` was provided.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if not enabled:
            return func

        if inspect.iscoroutinefunction(func):
            async_fn = cast("Callable[P, Awaitable[object]]", func)

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                async with _SIDE_EFFECT_LOCK:
                    patches = _apply_patches(strict)
                    try:
                        return await async_fn(*args, **kwargs)
                    finally:
                        _restore(patches)

            return cast("Callable[P, T]", async_wrapper)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with _SIDE_EFFECT_LOCK:
                patches = _apply_patches(strict)
                try:
                    return func(*args, **kwargs)
                finally:
                    _restore(patches)

        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator
