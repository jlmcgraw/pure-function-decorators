"""Temporarily strip globals from a function while it executes."""

from __future__ import annotations

import threading
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
else:  # pragma: no cover
    import collections.abc as _abc

    Callable = _abc.Callable

_GLOBAL_GUARD_LOCK = threading.RLock()
_P = ParamSpec("_P")
_T = TypeVar("_T")


def forbid_globals(
    *, allow: tuple[str, ...] = ()
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Block reads or writes to ``fn.__globals__`` except for an allow-list."""

    def decorator(fn: Callable[_P, _T]) -> Callable[_P, _T]:
        @wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            globals_map = fn.__globals__
            snapshot = dict(globals_map)
            minimal = {
                "__builtins__": snapshot.get("__builtins__", __builtins__),
                fn.__name__: fn,
            }
            for name in allow:
                if name in snapshot:
                    minimal[name] = snapshot[name]

            with _GLOBAL_GUARD_LOCK:
                globals_map.clear()
                globals_map.update(minimal)
                try:
                    return fn(*args, **kwargs)
                finally:
                    globals_map.clear()
                    globals_map.update(snapshot)

        return wrapper

    return decorator
