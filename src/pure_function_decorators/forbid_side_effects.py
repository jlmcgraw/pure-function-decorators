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
from typing import TYPE_CHECKING, NoReturn, ParamSpec, TypeVar, override

if TYPE_CHECKING:
    from collections.abc import Callable
else:  # pragma: no cover
    import collections.abc as _abc

    Callable = _abc.Callable

_P = ParamSpec("_P")
_T = TypeVar("_T")


class _HybridRLock:
    """Lock usable as both sync and async context manager."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def __enter__(self) -> _HybridRLock:
        self._lock.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._lock.release()

    async def __aenter__(self) -> _HybridRLock:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._lock.acquire)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self._lock.release()


_SIDE_EFFECT_LOCK = _HybridRLock()


def _trap(name: str) -> Callable[..., NoReturn]:
    """Return a callable that raises ``RuntimeError`` when invoked."""

    def _raiser(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError(f"Side effect blocked: {name}")

    return _raiser


class _TrapStdIO:
    """File-like object that rejects writes to stdout/stderr."""

    def write(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError("Side effect blocked: stdio write")

    def flush(self) -> None:
        """Provide a harmless flush implementation for callers that expect one."""
        return None


def _apply_patches() -> list[tuple[object, str, object]]:
    patches: list[tuple[object, str, object]] = []

    def patch(obj: object, attr: str, repl: object) -> None:
        original = getattr(obj, attr)
        setattr(obj, attr, repl)
        patches.append((obj, attr, original))

    patch(builtins, "print", _trap("print"))
    patch(builtins, "open", _trap("open"))

    patch(random, "random", _trap("random.random"))
    patch(random, "randint", _trap("random.randint"))
    patch(random, "randrange", _trap("random.randrange"))
    patch(random, "choice", _trap("random.choice"))
    patch(random, "shuffle", _trap("random.shuffle"))
    patch(secrets, "token_bytes", _trap("secrets.token_bytes"))
    patch(secrets, "token_hex", _trap("secrets.token_hex"))
    patch(secrets, "token_urlsafe", _trap("secrets.token_urlsafe"))
    patch(os, "urandom", _trap("os.urandom"))
    patch(uuid, "uuid4", _trap("uuid.uuid4"))

    patch(time, "time", _trap("time.time"))
    patch(time, "sleep", _trap("time.sleep"))
    patch(time, "monotonic", _trap("time.monotonic"))
    patch(time, "perf_counter", _trap("time.perf_counter"))

    class _TrapDateTime(datetime.datetime):
        @override
        @classmethod
        def now(cls, *_args: object, **_kwargs: object) -> NoReturn:
            raise RuntimeError("Side effect blocked: datetime.now")

        @override
        @classmethod
        def utcnow(cls, *_args: object, **_kwargs: object) -> NoReturn:
            raise RuntimeError("Side effect blocked: datetime.utcnow")

        @override
        @classmethod
        def today(cls, *_args: object, **_kwargs: object) -> NoReturn:
            raise RuntimeError("Side effect blocked: datetime.today")

    patch(datetime, "datetime", _TrapDateTime)

    patch(os, "getenv", _trap("os.getenv"))

    class _TrapEnviron(dict[str, object]):
        @override
        def __getitem__(self, _key: str) -> NoReturn:
            raise RuntimeError("Side effect blocked: os.environ[] read")

        @override
        def __setitem__(self, _key: str, _value: object) -> NoReturn:
            raise RuntimeError("Side effect blocked: os.environ[] write")

        @override
        def get(self, _key: str, _default: object | None = None) -> NoReturn:
            raise RuntimeError("Side effect blocked: os.environ.get")

        @override
        def __delitem__(self, _key: str) -> NoReturn:
            raise RuntimeError("Side effect blocked: os.environ del")

    patch(os, "environ", _TrapEnviron())

    patch(os, "system", _trap("os.system"))
    patch(os, "popen", _trap("os.popen"))
    patch(os, "_exit", _trap("os._exit"))
    patch(sys, "exit", _trap("sys.exit"))

    patch(subprocess, "run", _trap("subprocess.run"))
    patch(subprocess, "Popen", _trap("subprocess.Popen"))
    patch(subprocess, "call", _trap("subprocess.call"))
    patch(subprocess, "check_call", _trap("subprocess.check_call"))
    patch(subprocess, "check_output", _trap("subprocess.check_output"))

    patch(socket, "socket", _trap("socket.socket"))
    with suppress(Exception):
        import http.client as http_client

        patch(http_client, "HTTPConnection", _trap("http.client.HTTPConnection"))
        patch(http_client, "HTTPSConnection", _trap("http.client.HTTPSConnection"))

    patch(threading.Thread, "start", _trap("threading.Thread.start"))
    patch(multiprocessing.Process, "start", _trap("multiprocessing.Process.start"))
    patch(
        futures.ThreadPoolExecutor,
        "__init__",
        _trap("ThreadPoolExecutor.__init__"),
    )
    patch(
        futures.ProcessPoolExecutor,
        "__init__",
        _trap("ProcessPoolExecutor.__init__"),
    )

    patch(logging.Logger, "_log", _trap("logging"))
    patch(warnings, "warn", _trap("warnings.warn"))

    patch(atexit, "register", _trap("atexit.register"))

    patch(sys, "stdout", _TrapStdIO())
    patch(sys, "stderr", _TrapStdIO())

    with suppress(Exception):
        sqlite3 = importlib.import_module("sqlite3")
        patch(sqlite3, "connect", _trap("sqlite3.connect"))
    with suppress(Exception):
        psycopg2 = importlib.import_module("psycopg2")
        patch(psycopg2, "connect", _trap("psycopg2.connect"))
    with suppress(Exception):
        mysql_connector = importlib.import_module("mysql.connector")
        patch(
            mysql_connector,
            "connect",
            _trap("mysql.connector.connect"),
        )

    return patches


def _restore(patches: list[tuple[object, str, object]]) -> None:
    for obj, attr, original in reversed(patches):
        setattr(obj, attr, original)


def forbid_side_effects(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Reject attempts to perform common side effects while ``fn`` runs."""

    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def async_wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            async with _SIDE_EFFECT_LOCK:
                patches = _apply_patches()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    _restore(patches)

        return async_wrapper

    @wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        with _SIDE_EFFECT_LOCK:
            patches = _apply_patches()
            try:
                return fn(*args, **kwargs)
            finally:
                _restore(patches)

    return wrapper
