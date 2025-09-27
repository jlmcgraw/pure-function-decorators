import pickle
from functools import wraps


def enforce_deterministic(fn):
    cache = {}

    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = pickle.dumps((args, kwargs))
        result = fn(*args, **kwargs)
        if key in cache and cache[key] != result:
            raise ValueError("Non-deterministic output detected")
        cache[key] = result
        return result

    return wrapper
