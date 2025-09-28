"""Utilities for preventing in-place mutations performed by callables."""
# ruff: noqa: ANN401

from __future__ import annotations

import copy
import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, Final, cast, overload

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

_Path = tuple[str, ...]
_Diff = tuple[_Path, str]

_LOGGER: Final = logging.getLogger(__name__)

__all__ = ["immutable_arguments"]


def _describe_collection(items: Iterable[Any]) -> str:
    """Return a deterministic description of the provided collection.

    Parameters
    ----------
    items : Iterable[Any]
        Items whose representations should be summarized.

    Returns:
    -------
    str
        A human-readable summary of the iterable contents.
    """
    return "[" + ", ".join(sorted(repr(item) for item in items)) + "]"


def _compare_sequence(
    seq_a: Sequence[Any], seq_b: Sequence[Any], path: _Path
) -> _Diff | None:
    """Compare two sequences and return the first detected mutation.

    Parameters
    ----------
    seq_a : Sequence[Any]
        The sequence captured in the snapshot prior to invoking the function.
    seq_b : Sequence[Any]
        The sequence observed after the function executed.
    path : _Path
        The navigation path used for diagnostic messages.

    Returns:
    -------
    _Diff | None
        ``None`` if the sequences are identical, otherwise the path and
        description of the first difference encountered.
    """
    if len(seq_a) != len(seq_b):
        return (*path, "<len>"), f"{len(seq_a)} -> {len(seq_b)}"
    for index, (left, right) in enumerate(zip(seq_a, seq_b, strict=True)):
        diff = _first_diff(left, right, (*path, f"[{index}]"))
        if diff:
            return diff
    return None


def _first_diff(a: Any, b: Any, path: _Path = ()) -> _Diff | None:
    """Return the first difference between ``a`` and ``b`` (if any).

    Parameters
    ----------
    a : Any
        The value observed after the wrapped function executed.
    b : Any
        The snapshot of the value prior to function execution.
    path : _Path, optional
        The hierarchical path used to build informative error messages,
        by default ``()``.

    Returns:
    -------
    _Diff | None
        ``None`` if no mutation is detected, otherwise the path segment and
        description of the detected change.
    """
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

    a_obj: object = cast("object", a)
    b_obj: object = cast("object", b)
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


@overload
def immutable_arguments[**P, T](
    fn: Callable[P, T],
    *,
    warn_only: bool = False,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[P, T]: ...


@overload
def immutable_arguments[**P, T](
    *,
    warn_only: bool = False,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def immutable_arguments[**P, T](
    fn: Callable[P, T] | None = None,
    *,
    warn_only: bool = False,
    enabled: bool = True,
    strict: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]] | Callable[P, T]:
    """Prevent and surface in-place mutations performed by ``fn``.

    Parameters
    ----------
    fn : Callable[P, T] | None, optional
        The function to decorate. When omitted, the decorator is returned
        for deferred application.
    warn_only : bool, optional
        If ``True`` log detected mutations instead of raising
        ``RuntimeError``.
    enabled : bool, optional
        If ``False`` skip decorating and return ``fn`` unchanged.
    strict : bool, optional
        When ``False`` log warnings instead of raising ``RuntimeError`` when
        mutations are detected.

    Returns:
    -------
    Callable
        Either the decorated function or a decorator awaiting a function,
        depending on whether ``fn`` was provided.

    Notes:
    -----
    The decorator deep-copies all positional and keyword arguments, invokes
    ``fn`` with the copies, and compares the copies against further snapshots.
    Any mutation is surfaced according to ``warn_only``.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if not enabled:
            return func

        effective_strict = strict and not warn_only

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            frozen_memo: dict[int, object] = {}
            frozen_args = copy.deepcopy(args, frozen_memo)
            frozen_kwargs = copy.deepcopy(kwargs, frozen_memo)

            snapshot_memo: dict[int, object] = {}
            args_snapshot = copy.deepcopy(frozen_args, snapshot_memo)
            kwargs_snapshot = copy.deepcopy(frozen_kwargs, snapshot_memo)

            result = func(*frozen_args, **frozen_kwargs)

            for index, (current, snapshot) in enumerate(
                zip(frozen_args, args_snapshot, strict=True)
            ):
                diff = _first_diff(current, snapshot, path=(f"arg[{index}]",))
                if diff:
                    diff_path, message = diff
                    joined = "/".join(diff_path)
                    text = f"Argument mutated at {joined}: {message}"
                    if warn_only or not effective_strict:
                        _LOGGER.warning(text)
                        continue
                    raise RuntimeError(text)

            for key, current in frozen_kwargs.items():
                snapshot = kwargs_snapshot[key]
                diff = _first_diff(current, snapshot, path=(f"kwarg[{key!r}]",))
                if diff:
                    diff_path, message = diff
                    joined = "/".join(diff_path)
                    text = f"Argument mutated at {joined}: {message}"
                    if warn_only or not effective_strict:
                        _LOGGER.warning(text)
                        continue
                    raise RuntimeError(text)

            return result

        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator
