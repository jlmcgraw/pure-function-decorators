"""Utilities for detecting in-place mutations performed by callables."""
# ruff: noqa: ANN401

from __future__ import annotations

import copy
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
else:  # pragma: no cover - provide runtime aliases for introspection tools
    import collections.abc as _abc

    Callable = _abc.Callable
    Iterable = _abc.Iterable
    Mapping = _abc.Mapping
    Sequence = _abc.Sequence

_Path = tuple[str, ...]
_Diff = tuple[_Path, str]
_P = ParamSpec("_P")
_T = TypeVar("_T")


def _describe_collection(items: Iterable[Any]) -> str:
    return "[" + ", ".join(sorted(repr(item) for item in items)) + "]"


def _compare_sequence(
    seq_a: Sequence[Any], seq_b: Sequence[Any], path: _Path
) -> _Diff | None:
    if len(seq_a) != len(seq_b):
        return (*path, "<len>"), f"{len(seq_a)} -> {len(seq_b)}"
    for index, (left, right) in enumerate(zip(seq_a, seq_b, strict=True)):
        diff = _first_diff(left, right, (*path, f"[{index}]"))
        if diff:
            return diff
    return None


def _first_diff(a: Any, b: Any, path: _Path = ()) -> _Diff | None:
    """Return the first difference between ``a`` and ``b`` (if any)."""
    if type(a) is not type(b):
        return path, f"type {type(a).__name__} -> {type(b).__name__}"

    if isinstance(a, dict) and isinstance(b, dict):
        a_dict = cast("dict[object, object]", a)
        b_dict = cast("dict[object, object]", b)
        a_keys: set[object] = set(a_dict.keys())
        b_keys: set[object] = set(b_dict.keys())
        if a_keys != b_keys:
            missing = a_keys - b_keys
            added = b_keys - a_keys
            if missing:
                return (
                    *path,
                    "<dict-keys>",
                ), f"missing keys {_describe_collection(missing)}"
            if added:
                return (
                    *path,
                    "<dict-keys>",
                ), f"added keys {_describe_collection(added)}"
        for key in a_dict:
            diff = _first_diff(a_dict[key], b_dict[key], (*path, f"[{key!r}]"))
            if diff:
                return diff
        return None

    if isinstance(a, list) and isinstance(b, list):
        return _compare_sequence(
            cast("Sequence[Any]", a), cast("Sequence[Any]", b), path
        )

    if isinstance(a, tuple) and isinstance(b, tuple):
        return _compare_sequence(
            cast("Sequence[Any]", a), cast("Sequence[Any]", b), path
        )

    if isinstance(a, set) and isinstance(b, set):
        a_set: set[object] = cast("set[object]", a)
        b_set: set[object] = cast("set[object]", b)
        if a_set != b_set:
            removed_desc = _describe_collection(a_set - b_set)
            added_desc = _describe_collection(b_set - a_set)
            return path, f"set changed; -{removed_desc} +{added_desc}"
        return None

    if isinstance(a, frozenset) and isinstance(b, frozenset):
        a_items: set[object] = set(cast("Iterable[object]", a))
        b_items: set[object] = set(cast("Iterable[object]", b))
        if a_items != b_items:
            removed_desc = _describe_collection(a_items - b_items)
            added_desc = _describe_collection(b_items - a_items)
            return path, f"set changed; -{removed_desc} +{added_desc}"
        return None

    a_obj: object = cast(object, a)
    b_obj: object = cast(object, b)
    if hasattr(a_obj, "__dict__") and hasattr(b_obj, "__dict__"):
        a_mapping = cast("Mapping[str, Any]", a_obj.__dict__)
        b_mapping = cast("Mapping[str, Any]", b_obj.__dict__)
        return _first_diff(a_mapping, b_mapping, (*path, ".__dict__"))

    if a_obj != b_obj:
        left_repr = repr(a_obj)
        right_repr = repr(b_obj)
        if len(left_repr) > 200:
            left_repr = f"{left_repr[:197]}..."
        if len(right_repr) > 200:
            right_repr = f"{right_repr[:197]}..."
        return path, f"value {left_repr} -> {right_repr}"
    return None


def detect_immutable(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Raise ``RuntimeError`` if ``fn`` mutates its arguments in-place."""

    @wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        memo: dict[int, object] = {}
        args_snapshot = copy.deepcopy(args, memo)
        kwargs_snapshot = copy.deepcopy(kwargs, memo)

        result = fn(*args, **kwargs)

        for index, (original, snapshot) in enumerate(
            zip(args, args_snapshot, strict=True)
        ):
            diff = _first_diff(original, snapshot, path=(f"arg[{index}]",))
            if diff:
                diff_path, message = diff
                joined = "/".join(diff_path)
                raise RuntimeError(f"Argument mutated at {joined}: {message}")

        for key, original in kwargs.items():
            snapshot = kwargs_snapshot[key]
            diff = _first_diff(original, snapshot, path=(f"kwarg[{key!r}]",))
            if diff:
                diff_path, message = diff
                joined = "/".join(diff_path)
                raise RuntimeError(f"Argument mutated at {joined}: {message}")

        return result

    return wrapper
