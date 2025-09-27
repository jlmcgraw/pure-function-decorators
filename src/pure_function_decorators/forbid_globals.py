# Forbid access to module globals during the wrapped call by temporarily
# stripping the function's globals dict to a minimal whitelist.
# Not thread-safe across callers of the *same module*; use only in tests.

import threading
from functools import wraps
from types import FunctionType

_GLOBAL_GUARD_LOCK = threading.RLock()


def forbid_globals(*, allow: tuple[str, ...] = ()):
    """
    Blocks reads/writes to fn.__globals__ by clearing it during the call.
    Whitelist names via `allow` (e.g., recursion, constants you explicitly permit).

    - Always preserves __builtins__.
    - Adds the function's own name to allow recursion.
    - Restores the original globals mapping after the call.
    - Side effect: other code in the same module sees the stripped globals during the call.

    Example:
        @forbid_globals()
        def f(x): return x + CONST   # raises NameError (global blocked)

        @forbid_globals(allow=("CONST",))
        def g(x): return x + CONST   # allowed
    """

    def decorator(fn: FunctionType):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            g = fn.__globals__
            snapshot = dict(g)
            minimal = {
                "__builtins__": snapshot.get("__builtins__", __builtins__),
                fn.__name__: fn,
            }
            for name in allow:
                if name in snapshot:
                    minimal[name] = snapshot[name]

            with _GLOBAL_GUARD_LOCK:
                g.clear()
                g.update(minimal)
                try:
                    return fn(*args, **kwargs)
                finally:
                    g.clear()
                    g.update(snapshot)

        return wrapper

    return decorator
