[![Latest Version](https://img.shields.io/pypi/v/pure-function-decorators?label=pypi-version&logo=python&style=plastic)](https://pypi.org/project/pure-function-decorators/)
[![Python Versions](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fjlmcgraw%2Fpure-function-decorators%2Fmain%2Fpyproject.toml&style=plastic&logo=python&label=python-versions)](https://www.python.org/)
[![Build Status](https://github.com/jlmcgraw/pure-function-decorators/actions/workflows/main.yml/badge.svg)](https://github.com/jlmcgraw/pure-function-decorators/actions/workflows/main.yml)
[![Documentation Status](https://github.com/jlmcgraw/pure-function-decorators/actions/workflows/docs.yml/badge.svg)](https://jlmcgraw.github.io/pure-function-decorators/)

# pure-function-decorators

_Decorators to try to enforce various types of function purity in Python_

Mostly vibe-coded, though I hope to whittle down any issues 

## Super-quick Start

Requires: Python 3.10 to 3.13

Install through pip:

```bash
pip install pure-function-decorators
```

```python
from pure_function_decorators import (
    enforce_deterministic,
    forbid_globals,
    forbid_side_effects,
    immutable_arguments,
)


@forbid_globals()
def bad(x):
    return x + CONST

CONST = 10
bad(1)   # Raises NameError
```

## Documentation

The complete documentation can be found at the
[pure-function-decorators home page](https://jlmcgraw.github.io/pure-function-decorators)

# Features

## Existing decorators

- `immutable_arguments` deep-copies inputs before invoking the wrapped callable so callers never observe in-place mutations. By default the decorator raises when a mutation is detected, and it can instead log warnings with `warn_only=True`.
- `enforce_deterministic` reruns a function and compares its results so you can gate functions that rely on deterministic behavior.
- `forbid_globals` prevents a function from reading or mutating module-level state by sandboxing its globals. Pass
  `check_names=True` to also fail decoration when bytecode references globals outside the allow-list, or set
  `sandbox=False` to keep only the bytecode-based validation.
- `forbid_side_effects` instruments builtin operations that commonly mutate process state (e.g. file writes, subprocess launches) to surface accidental side effects.

## Future purity checks to explore

The current decorators focus on globals, determinism, and structural immutability. Additional checks that build on the same inspection hooks could include:

- **Non-deterministic source guards** &mdash; wrap time-, randomness-, and UUID-related modules (`time`, `datetime`, `random`, `uuid`, `secrets`) to ensure a supposedly pure function does not sample entropy or wall-clock timestamps.
- **Environment isolation** &mdash; raise when a function touches environment variables, current working directory, or other process-wide configuration through `os.environ`, `os.chdir`, or similar APIs.
- **I/O safelists** &mdash; expand the `forbid_side_effects` strategy with dedicated helpers that specifically deny file, socket, or HTTP operations unless a pure-safe allowlist is provided.
- **Mutable default detection** &mdash; detect functions whose default arguments or closed-over state are mutable so callers do not accidentally share state across invocations.
- **Dependency purity enforcement** &mdash; verify that functions only call other decorated or safelisted pure functions by walking the bytecode or AST.

These ideas could live alongside the existing decorators as optional opt-in guards so projects can combine them to match their definition of purity.

## Frequently asked questions

### Can these decorators be enabled globally, like `perl`'s `strict` pragma?

No. Python does not provide a hook that automatically wraps every function that is imported or defined after a module loads. The decorators in this project operate by returning a new callable, so each target function (or method) has to be wrapped explicitly. You can build your own helpers that iterate over a module or class and decorate selected callables, but the library cannot apply itself universally without the caller opting in on a per-function basis.

### What about leaning on the descriptor protocol to auto-wrap methods?

Descriptors only help when attribute access goes through a class that you control, and Python already turns functions defined on a class into descriptors that bind methods at lookup time. Swapping in a custom descriptor still requires you to opt in for each attribute you expose, and it cannot cover free functions or methods defined on classes outside your control. You could build a metaclass or `__setattr__` hook that decorates attributes as they are assigned, but that still imposes an explicit opt-in boundary (the metaclass or base class) rather than letting a library blanket the entire interpreter.
