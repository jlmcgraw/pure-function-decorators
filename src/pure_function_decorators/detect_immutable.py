import copy
from functools import wraps
from typing import Any, Optional, Tuple


def _first_diff(
    a: Any, b: Any, path: Tuple[str, ...] = ()
) -> Optional[Tuple[Tuple[str, ...], str]]:
    # Type changed
    if type(a) is not type(b):
        return path, f"type {type(a).__name__} -> {type(b).__name__}"

    # Dicts
    if isinstance(a, dict):
        ak, bk = set(a.keys()), set(b.keys())
        if ak != bk:
            missing = ak - bk
            added = bk - ak
            if missing:
                return path + ("<dict-keys>",), f"missing keys {sorted(missing)!r}"
            if added:
                return path + ("<dict-keys>",), f"added keys {sorted(added)!r}"
        for k in a:
            d = _first_diff(a[k], b[k], path + (f"[{k!r}]",))
            if d:
                return d
        return None

    # Lists / tuples
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return path + ("<len>",), f"{len(a)} -> {len(b)}"
        for i, (ai, bi) in enumerate(zip(a, b)):
            d = _first_diff(ai, bi, path + (f"[{i}]",))
            if d:
                return d
        return None

    # Sets / frozensets
    if isinstance(a, (set, frozenset)):
        if a != b:
            removed = a - b
            added = b - a
            return path, f"set changed; -{sorted(removed)!r} +{sorted(added)!r}"
        return None

    # Dataclass/objects with __dict__ (shallow heuristic)
    if hasattr(a, "__dict__") and hasattr(b, "__dict__"):
        return _first_diff(a.__dict__, b.__dict__, path + (".__dict__",))

    # Fallback equality
    if a != b:
        # Truncate long reprs for readability
        ra = repr(a)
        rb = repr(b)
        if len(ra) > 200:
            ra = ra[:197] + "..."
        if len(rb) > 200:
            rb = rb[:197] + "..."
        return path, f"value {ra} -> {rb}"
    return None


def detect_immutable(fn):
    """
    Detects in-place modifications of any passed-in argument.
    Takes deep snapshots before the call and diffs after the call.
    Not thread-safe. Does not catch mutations that occur after return (e.g., background threads).
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Deep snapshots (preserve aliasing graph via memo)
        memo = {}
        args_snapshot = copy.deepcopy(args, memo)
        kwargs_snapshot = copy.deepcopy(kwargs, memo)

        result = fn(*args, **kwargs)

        # Compare positional args
        for i, (orig, snap) in enumerate(zip(args, args_snapshot)):
            diff = _first_diff(orig, snap, path=(f"arg[{i}]",))
            if diff:
                path, msg = diff
                raise RuntimeError(f"Argument mutated at {'/'.join(path)}: {msg}")

        # Compare kwargs
        for k in kwargs:
            orig = kwargs[k]
            snap = kwargs_snapshot[k]
            diff = _first_diff(orig, snap, path=(f"kwarg[{k!r}]",))
            if diff:
                path, msg = diff
                raise RuntimeError(f"Argument mutated at {'/'.join(path)}: {msg}")

        return result

    return wrapper
