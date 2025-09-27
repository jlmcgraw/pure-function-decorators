import builtins
import dis
import types
from typing import Iterable

_GLOBAL_OPS = {"LOAD_GLOBAL", "STORE_GLOBAL", "DELETE_GLOBAL"}
_IMPORT_OPS = {"IMPORT_NAME"}


def _collect_global_names(
    code: types.CodeType,
    include_store_delete: bool = True,
    include_imports: bool = True,
) -> set[str]:
    """Recursively collect global-like names referenced by `code` and its nested code objects."""
    ops = {"LOAD_GLOBAL"}
    if include_store_delete:
        ops |= _GLOBAL_OPS - {"LOAD_GLOBAL"}

    names: set[str] = set()
    for ins in dis.get_instructions(code):
        if ins.opname in ops:
            # LOAD_/STORE_/DELETE_GLOBAL argval is the identifier name
            names.add(ins.argval)
        elif include_imports and ins.opname in _IMPORT_OPS:
            # IMPORT_NAME argval is the module/package name string
            names.add(ins.argval)

    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            names |= _collect_global_names(const, include_store_delete, include_imports)

    return names


def forbid_global_names(
    _fn=None,
    *,
    allow: Iterable[str] = (),
    allow_builtins: bool = True,
    include_store_delete: bool = True,
    include_imports: bool = True,
):
    """
    Decorator or decorator factory that rejects functions referencing globals
    outside an allow-list. Works as `@reject_global_names` or `@reject_global_names(...)`.

    Options:
      - allow: iterable of names to permit (e.g., constants).
      - allow_builtins: if True, whitelist all builtins.
      - include_store_delete: if True, also reject STORE_GLOBAL/DELETE_GLOBAL.
      - include_imports: if True, treat IMPORT_NAME as a global dependency.
    """
    allow_set = set(allow)
    if allow_builtins:
        allow_set |= set(builtins.__dict__.keys())

    def _decorate(fn):
        used = _collect_global_names(
            fn.__code__,
            include_store_delete=include_store_delete,
            include_imports=include_imports,
        )
        # Allow recursion (function referencing itself by name)
        used.discard(fn.__name__)
        # Filter against the allow-list
        bad = sorted(n for n in used if n not in allow_set)
        if bad:
            raise RuntimeError(f"Global names referenced: {bad}")
        return fn

    # Support both `@reject_global_names` and `@reject_global_names(...)`
    if _fn is None:
        return _decorate
    else:
        return _decorate(_fn)
