"""Utilities to forbid access to globals by name or at runtime."""

from __future__ import annotations

import builtins
import dis
import inspect
import logging
import types
from functools import wraps
from typing import TYPE_CHECKING, Final, cast, overload

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable

_GLOBAL_OPS: Final = {"LOAD_GLOBAL", "STORE_GLOBAL", "DELETE_GLOBAL"}
_IMPORT_OPS: Final = {"IMPORT_NAME"}

_LOGGER = logging.getLogger(__name__)


def _build_minimal_globals(
    fn: Callable[..., object], allow: tuple[str, ...]
) -> dict[str, object]:
    """Return a globals mapping limited to the provided allow-list.

    Parameters
    ----------
    fn : Callable[P, T]
        The function whose globals should be mirrored.
    allow : tuple[str, ...]
        Names that remain accessible to the cloned function.

    Returns:
    -------
    dict[str, object]
        A globals dictionary containing only the whitelisted names and
        essential module metadata.
    """
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
    fn: Callable[..., object], minimal: dict[str, object]
) -> Callable[..., object]:
    """Create a clone of ``fn`` that uses ``minimal`` as its globals mapping.

    Parameters
    ----------
    fn : Callable[P, T]
        The function to clone with restricted globals.
    minimal : dict[str, object]
        The globals dictionary the clone should operate with.

    Returns:
    -------
    Callable[P, T]
        A function object that executes ``fn``'s code inside the sandbox.
    """
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
    return cast("Callable[..., object]", sandboxed)


def _collect_global_names(
    code: types.CodeType,
    include_store_delete: bool = True,
    include_imports: bool = True,
) -> set[str]:
    """Recursively collect global-like names referenced by ``code``.

    Parameters
    ----------
    code : types.CodeType
        The code object to analyze.
    include_store_delete : bool, optional
        Whether ``STORE_GLOBAL`` and ``DELETE_GLOBAL`` operations should be
        considered, by default ``True``.
    include_imports : bool, optional
        Whether import operations should be treated as global access, by
        default ``True``.

    Returns:
    -------
    set[str]
        All global names referenced by the code object and its nested
        constants.
    """
    ops = {"LOAD_GLOBAL"}
    if include_store_delete:
        ops |= _GLOBAL_OPS - {"LOAD_GLOBAL"}

    names: set[str] = set()
    for ins in dis.get_instructions(code):
        if ins.opname in ops or (include_imports and ins.opname in _IMPORT_OPS):
            names.add(ins.argval)

    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            names |= _collect_global_names(const, include_store_delete, include_imports)

    return names


@overload
def forbid_globals[**P, T](
    fn: Callable[P, T],
    *,
    allow: Iterable[str] = (),
    allow_builtins: bool = True,
    include_store_delete: bool = True,
    include_imports: bool = True,
    sandbox: bool = True,
    check_names: bool = False,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[P, T]: ...


@overload
def forbid_globals[**P, T](
    fn: None = None,
    *,
    allow: Iterable[str] = (),
    allow_builtins: bool = True,
    include_store_delete: bool = True,
    include_imports: bool = True,
    sandbox: bool = True,
    check_names: bool = False,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def forbid_globals[**P, T](
    fn: Callable[P, T] | None = None,
    *,
    allow: Iterable[str] = (),
    allow_builtins: bool = True,
    include_store_delete: bool = True,
    include_imports: bool = True,
    sandbox: bool = True,
    check_names: bool = False,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]] | Callable[P, T]:
    """Restrict global access via name checking and/or runtime sandboxing.

    Parameters
    ----------
    fn : Callable[P, T] | None, optional
        The function to wrap. When omitted the decorator is returned for
        later application.
    allow : Iterable[str], optional
        Additional global names the wrapped function may reference, by
        default ``()``.
    allow_builtins : bool, optional
        If ``True`` the builtin namespace remains available, by default ``True``.
    include_store_delete : bool, optional
        Whether to treat ``STORE_GLOBAL``/``DELETE_GLOBAL`` as violations, by
        default ``True``.
    include_imports : bool, optional
        Whether import opcodes should trigger the name check, by default ``True``.
    sandbox : bool, optional
        If ``True`` execute the function with a restricted globals dictionary.
    check_names : bool, optional
        When ``True`` statically inspect the function for disallowed names.
    enabled : bool, optional
        If ``False`` skip decorating and return ``fn`` unchanged.
    strict : bool, optional
        When ``False`` log warnings instead of raising ``RuntimeError`` during
        name checking.

    Returns:
    -------
    Callable
        Either the decorated function or a decorator awaiting a function,
        depending on whether ``fn`` was provided.

    Raises:
    ------
    RuntimeError
        If ``check_names`` is enabled and a disallowed global is detected.
    """
    allowed_tuple = tuple(allow)
    allowed_set = set(allowed_tuple)
    if check_names and allow_builtins:
        allowed_set |= set(builtins.__dict__.keys())

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        if not enabled:
            return fn
        if check_names:
            used = _collect_global_names(
                fn.__code__,
                include_store_delete=include_store_delete,
                include_imports=include_imports,
            )
            used.discard(fn.__name__)
            disallowed = sorted(name for name in used if name not in allowed_set)
            if disallowed:
                message = f"Global names referenced: {disallowed}"
                if strict:
                    raise RuntimeError(message)
                _LOGGER.warning(message)

        if not sandbox:
            return fn

        if inspect.iscoroutinefunction(fn):
            async_fn = cast("Callable[P, Awaitable[object]]", fn)

            @wraps(fn)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                sandboxed = cast(
                    "Callable[P, Awaitable[object]]",
                    _make_sandboxed(
                        async_fn, _build_minimal_globals(async_fn, allowed_tuple)
                    ),
                )
                return await sandboxed(*args, **kwargs)

            return cast("Callable[P, T]", async_wrapper)

        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            sandboxed = cast(
                "Callable[P, T]",
                _make_sandboxed(fn, _build_minimal_globals(fn, allowed_tuple)),
            )
            return sandboxed(*args, **kwargs)

        return wrapper

    if fn is None:
        return decorator
    return decorator(fn)
