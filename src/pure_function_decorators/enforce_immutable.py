import copy
from functools import wraps


def enforce_immutable(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        frozen_args = copy.deepcopy(args)
        frozen_kwargs = copy.deepcopy(kwargs)
        result = fn(*frozen_args, **frozen_kwargs)
        return result

    return wrapper
