"""Decorator that rejects functions referencing disallowed global names."""

from __future__ import annotations

import builtins
import dis
import types
from typing import TYPE_CHECKING, ParamSpec, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
else:  # pragma: no cover
    import collections.abc as _abc

    Callable = _abc.Callable
    Iterable = _abc.Iterable

_GLOBAL_OPS = {"LOAD_GLOBAL", "STORE_GLOBAL", "DELETE_GLOBAL"}
_IMPORT_OPS = {"IMPORT_NAME"}
_P = ParamSpec("_P")
_T = TypeVar("_T")


def _collect_global_names(
    code: types.CodeType,
    include_store_delete: bool = True,
    include_imports: bool = True,
) -> set[str]:
    """Recursively collect global-like names referenced by ``code``."""
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
def forbid_global_names(
    fn: Callable[_P, _T],
    *,
    allow: Iterable[str] = (),
    allow_builtins: bool = True,
    include_store_delete: bool = True,
    include_imports: bool = True,
) -> Callable[_P, _T]: ...


@overload
def forbid_global_names(
    fn: None = None,
    *,
    allow: Iterable[str] = (),
    allow_builtins: bool = True,
    include_store_delete: bool = True,
    include_imports: bool = True,
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]: ...


def forbid_global_names(
    fn: Callable[_P, _T] | None = None,
    *,
    allow: Iterable[str] = (),
    allow_builtins: bool = True,
    include_store_delete: bool = True,
    include_imports: bool = True,
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]] | Callable[_P, _T]:
    """Disallow access to global names outside the provided allow-list."""
    allow_set = set(allow)
    if allow_builtins:
        allow_set |= set(builtins.__dict__.keys())

    def _decorate(fn: Callable[_P, _T]) -> Callable[_P, _T]:
        used = _collect_global_names(
            fn.__code__,
            include_store_delete=include_store_delete,
            include_imports=include_imports,
        )
        used.discard(fn.__name__)
        disallowed = sorted(name for name in used if name not in allow_set)
        if disallowed:
            raise RuntimeError(f"Global names referenced: {disallowed}")
        return fn

    if fn is None:
        return _decorate
    return _decorate(fn)
