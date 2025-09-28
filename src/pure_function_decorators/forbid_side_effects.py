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
from typing import (
    Final,
    NoReturn,
    ParamSpec,
    Self,
    TypeVar,
    cast,
    overload,
    override,
)
from collections.abc import Awaitable, Callable, Iterator, MutableMapping

_P = ParamSpec("_P")
_T = TypeVar("_T")
_DecoratedFunc = TypeVar("_DecoratedFunc", bound=Callable[_P, _T])
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
    try:
        sys.__stderr__.write(f"{message}\n")
        sys.__stderr__.flush()
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


class _TrapStdIO:
    """File-like object that reacts to writes to stdout/stderr."""

    def __init__(self, *, strict: bool, original: object | None = None) -> None:
        """Store behaviour configuration for stdio interception."""
        self._strict = strict
        self._original = original

    def write(self, *args: object, **kwargs: object) -> object:
        """Handle writes by raising or delegating with a warning."""
        message = "Side effect blocked: stdio write"
        if self._strict:
            raise RuntimeError(message)
        _emit_warning(message)
        if self._original is not None and hasattr(self._original, "write"):
            return self._original.write(*args, **kwargs)
        return None

    def flush(self) -> object:
        """Provide a harmless flush implementation for callers that expect one."""
        if self._original is not None and hasattr(self._original, "flush"):
            return self._original.flush()
        return None

    def __getattr__(self, item: str) -> object:
        """Delegate attribute access to the wrapped stream when available."""
        if self._original is None:
            raise AttributeError(item)
        return getattr(self._original, item)


class _TrapEnviron(MutableMapping[str, str]):
    """Proxy object that enforces side-effect policy for ``os.environ``."""

    def __init__(self, *, strict: bool, original: MutableMapping[str, str]) -> None:
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

    @override
    def get(
        self, key: str, default: str | None = None
    ) -> str | None:  # pragma: no cover - passthrough
        message = "Side effect blocked: os.environ.get"
        if self._strict:
            raise RuntimeError(message)
        _emit_warning(message)
        return self._original.get(key, default)


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

    original_datetime = datetime.datetime

    if strict:

        class _TrapDateTime(original_datetime):
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

        patch_value(datetime, "datetime", lambda _orig: _TrapDateTime)
    else:

        class _WarnDateTime(original_datetime):
            @override
            @classmethod
            def now(cls, tz: datetime.tzinfo | None = None) -> datetime.datetime:
                _emit_warning("Side effect blocked: datetime.now")
                return (
                    original_datetime.now(tz)
                    if tz is not None
                    else original_datetime.now()
                )

            @override
            @classmethod
            def utcnow(cls) -> datetime.datetime:
                _emit_warning("Side effect blocked: datetime.utcnow")
                return original_datetime.now(datetime.UTC)

            @override
            @classmethod
            def today(cls) -> datetime.datetime:
                _emit_warning("Side effect blocked: datetime.today")
                return original_datetime.today()

        patch_value(datetime, "datetime", lambda _orig: _WarnDateTime)

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
def forbid_side_effects(
    fn: _DecoratedFunc, *, enabled: bool = True, strict: bool = True
) -> _DecoratedFunc: ...


@overload
def forbid_side_effects(
    *, enabled: bool = True, strict: bool = True
) -> Callable[[_DecoratedFunc], _DecoratedFunc]: ...


def forbid_side_effects(
    fn: _DecoratedFunc | None = None,
    *,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[[_DecoratedFunc], _DecoratedFunc] | _DecoratedFunc:
    """Reject attempts to perform common side effects while ``fn`` runs.

    Parameters
    ----------
    fn : Callable[_P, _T] | None, optional
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

    def decorator(func: _DecoratedFunc) -> _DecoratedFunc:
        if not enabled:
            return func

        if inspect.iscoroutinefunction(func):
            async_fn = cast("Callable[_P, Awaitable[object]]", func)

            @wraps(func)
            async def async_wrapper(*args: _P.args, **kwargs: _P.kwargs) -> object:
                async with _SIDE_EFFECT_LOCK:
                    patches = _apply_patches(strict)
                    try:
                        return await async_fn(*args, **kwargs)
                    finally:
                        _restore(patches)

            return cast("_DecoratedFunc", async_wrapper)

        @wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            with _SIDE_EFFECT_LOCK:
                patches = _apply_patches(strict)
                try:
                    return func(*args, **kwargs)
                finally:
                    _restore(patches)

        return cast("_DecoratedFunc", wrapper)

    if fn is not None:
        return decorator(fn)
    return decorator
