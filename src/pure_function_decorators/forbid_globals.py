"""Temporarily strip globals from a function while it executes."""

from __future__ import annotations

import inspect
import types
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
else:  # pragma: no cover
    import collections.abc as _abc

    Callable = _abc.Callable

_P = ParamSpec("_P")
_T = TypeVar("_T")


def _build_minimal_globals(
    fn: Callable[_P, _T], allow: tuple[str, ...]
) -> dict[str, object]:
    """Return a globals mapping limited to the provided allow-list."""

    source_globals = fn.__globals__
    minimal: dict[str, object] = {
        "__builtins__": source_globals.get("__builtins__", __builtins__),
        "__name__": source_globals.get("__name__", fn.__module__),
        "__package__": source_globals.get("__package__"),
        "__spec__": source_globals.get("__spec__"),
        "__loader__": source_globals.get("__loader__"),
        "__file__": source_globals.get("__file__"),
        "__cached__": source_globals.get("__cached__"),
    }
    for name in allow:
        if name in source_globals:
            minimal[name] = source_globals[name]
    return minimal


def _make_sandboxed(
    fn: Callable[_P, _T], minimal: dict[str, object]
) -> Callable[_P, _T]:
    """Create a clone of ``fn`` that uses ``minimal`` as its globals mapping."""

    sandboxed = types.FunctionType(
        fn.__code__,
        minimal,
        fn.__name__,
        fn.__defaults__,
        fn.__closure__,
    )
    sandboxed.__module__ = fn.__module__
    sandboxed.__doc__ = fn.__doc__
    sandboxed.__qualname__ = fn.__qualname__
    sandboxed.__kwdefaults__ = getattr(fn, "__kwdefaults__", None)
    sandboxed.__annotations__ = getattr(fn, "__annotations__", {}).copy()
    minimal[fn.__name__] = sandboxed
    return sandboxed


def forbid_globals(
    *, allow: tuple[str, ...] = ()
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Block reads or writes to ``fn.__globals__`` except for an allow-list."""

    def decorator(fn: Callable[_P, _T]) -> Callable[_P, _T]:
        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
                sandboxed = _make_sandboxed(fn, _build_minimal_globals(fn, allow))
                return await sandboxed(*args, **kwargs)

            return async_wrapper

        @wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            sandboxed = _make_sandboxed(fn, _build_minimal_globals(fn, allow))
            return sandboxed(*args, **kwargs)

        return wrapper

    return decorator
