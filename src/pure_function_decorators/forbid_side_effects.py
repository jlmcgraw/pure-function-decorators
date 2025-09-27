import atexit
import builtins
import concurrent.futures as futures
import datetime
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
from functools import wraps

# Heuristic purity guard: blocks common side effects during the wrapped call.
# Restores originals after execution. Not thread-safe. Best for tests.


def _trap(name):
    def _raiser(*a, **k):
        raise RuntimeError(f"Side effect blocked: {name}")

    return _raiser


class _TrapStdIO:
    def write(self, *_a, **_k):
        raise RuntimeError("Side effect blocked: stdio write")

    def flush(self):  # some code calls flush unconditionally
        pass


def forbid_side_effects(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        patches = []

        def patch(obj, attr, repl):
            original = getattr(obj, attr)
            setattr(obj, attr, repl)
            patches.append((obj, attr, original))

        # builtins I/O and process
        patch(builtins, "print", _trap("print"))
        patch(builtins, "open", _trap("open"))

        # randomness
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

        # time
        patch(time, "time", _trap("time.time"))
        patch(time, "sleep", _trap("time.sleep"))
        patch(time, "monotonic", _trap("time.monotonic"))
        patch(time, "perf_counter", _trap("time.perf_counter"))

        # datetime (replace class with trap subclass)
        _orig_datetime_cls = datetime.datetime

        class _TrapDateTime(datetime.datetime):  # type: ignore[misc]
            @classmethod
            def now(cls, *a, **k):
                raise RuntimeError("Side effect blocked: datetime.now")

            @classmethod
            def utcnow(cls, *a, **k):
                raise RuntimeError("Side effect blocked: datetime.utcnow")

            @classmethod
            def today(cls, *a, **k):
                raise RuntimeError("Side effect blocked: datetime.today")

        datetime.datetime = _TrapDateTime  # type: ignore[assignment]

        # environment
        patch(os, "getenv", _trap("os.getenv"))
        # wrap os.environ mapping to block get/set/del
        _orig_environ = os.environ

        class _TrapEnviron(dict):
            def __getitem__(self, k):
                raise RuntimeError("Side effect blocked: os.environ[] read")

            def __setitem__(self, k, v):
                raise RuntimeError("Side effect blocked: os.environ[] write")

            def get(self, k, d=None):
                raise RuntimeError("Side effect blocked: os.environ.get")

            def __delitem__(self, k):
                raise RuntimeError("Side effect blocked: os.environ del")

        os.environ = _TrapEnviron()  # type: ignore[assignment]

        # OS commands and process control
        patch(os, "system", _trap("os.system"))
        patch(os, "popen", _trap("os.popen"))
        patch(os, "_exit", _trap("os._exit"))
        patch(sys, "exit", _trap("sys.exit"))

        # subprocess
        patch(subprocess, "run", _trap("subprocess.run"))
        patch(subprocess, "Popen", _trap("subprocess.Popen"))
        patch(subprocess, "call", _trap("subprocess.call"))
        patch(subprocess, "check_call", _trap("subprocess.check_call"))
        patch(subprocess, "check_output", _trap("subprocess.check_output"))

        # networking
        patch(socket, "socket", _trap("socket.socket"))
        # optional: block common high-level clients if present
        try:
            import http.client as http_client

            patch(http_client, "HTTPConnection", _trap("http.client.HTTPConnection"))
            patch(http_client, "HTTPSConnection", _trap("http.client.HTTPSConnection"))
        except Exception:
            pass

        # threading / multiprocessing / executors
        patch(threading.Thread, "start", _trap("threading.Thread.start"))
        patch(multiprocessing.Process, "start", _trap("multiprocessing.Process.start"))
        patch(
            futures.ThreadPoolExecutor, "__init__", _trap("ThreadPoolExecutor.__init__")
        )
        patch(
            futures.ProcessPoolExecutor,
            "__init__",
            _trap("ProcessPoolExecutor.__init__"),
        )

        # logging and warnings
        patch(logging.Logger, "_log", _trap("logging"))
        patch(warnings, "warn", _trap("warnings.warn"))

        # atexit
        patch(atexit, "register", _trap("atexit.register"))

        # stdio writes (avoid swapping objects; trap writes instead)
        _saved_stdout, _saved_stderr = sys.stdout, sys.stderr
        sys.stdout = _TrapStdIO()  # type: ignore[assignment]
        sys.stderr = _TrapStdIO()  # type: ignore[assignment]

        # optional: sqlite3 and common DB connectors if available
        try:
            import sqlite3

            patch(sqlite3, "connect", _trap("sqlite3.connect"))
        except Exception:
            pass
        try:
            import psycopg2  # type: ignore

            patch(psycopg2, "connect", _trap("psycopg2.connect"))
        except Exception:
            pass
        try:
            import mysql.connector as mysql_connector  # type: ignore

            patch(mysql_connector, "connect", _trap("mysql.connector.connect"))
        except Exception:
            pass

        try:
            return fn(*args, **kwargs)
        finally:
            # restore patched attributes
            for obj, attr, original in reversed(patches):
                setattr(obj, attr, original)
            # restore datetime class
            datetime.datetime = _orig_datetime_cls  # type: ignore[assignment]
            # restore environ and stdio
            os.environ = _orig_environ  # type: ignore[assignment]
            sys.stdout = _saved_stdout  # type: ignore[assignment]
            sys.stderr = _saved_stderr  # type: ignore[assignment]

    return wrapper
