[![Latest Version](https://img.shields.io/pypi/v/pure-function-decorators?label=pypi-version&logo=python&style=plastic)](https://pypi.org/project/pure-function-decorators/)
[![Python Versions](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fjlmcgraw%2Fpure-function-decorators%2Fmain%2Fpyproject.toml&style=plastic&logo=python&label=python-versions)](https://www.python.org/)
[![Build Status](https://github.com/jlmcgraw/pure-function-decorators/actions/workflows/main.yml/badge.svg)](https://github.com/jlmcgraw/pure-function-decorators/actions/workflows/main.yml)
[![Documentation Status](https://github.com/jlmcgraw/pure-function-decorators/actions/workflows/docs.yml/badge.svg)](https://jlmcgraw.github.io/pure-function-decorators/)

# pure-function-decorators

_Decorators to try to enforce various types of function purity in Python_

This is obviously mostly vibe-coded and perhaps better suited to static analysis anyhow.  I'm using it as an exercise and
any actual utility is just a bonus

## Super-quick Start

Requires: Python >= 3.12

The implementation adopts modern standard-library typing helpers such as
``typing.override`` and ``typing.Self``, so earlier interpreters are not
supported.

Install through pip:

```bash
pip install pure-function-decorators
```

```python
from pure_function_decorators import forbid_globals


@forbid_globals()
def bad(x):
    return x + CONST


CONST = 10
bad(1)  # Raises NameError
```

```python
import datetime

from pure_function_decorators import enforce_deterministic


@enforce_deterministic
def bad():
    return datetime.datetime.now().microsecond


print(bad())
print(bad())  # raises ValueError
```

## Documentation

The complete documentation can be found at the
[pure-function-decorators home page](https://jlmcgraw.github.io/pure-function-decorators)

# Features

## Existing decorators

- `immutable_arguments` deep-copies inputs before invoking the wrapped callable so callers never see in-place mutations.
    - By default, the decorator raises when a mutation is detected.
    - Use `warn_only=True` or `strict=False` to log warnings instead of raising, or `enabled=False` to bypass checks.
- `enforce_deterministic` ensures that the decorated function consistently returns the same result for the same
  parameters.
    - Set `strict=False` to emit warnings when nondeterministic behaviour is observed or `enabled=False` to skip wrapping.
- `forbid_globals` prevents a function from reading or mutating module-level state by sandboxing its globals.
    - `check_names=True` to also fail decoration when bytecode references globals outside the allow-list, or set
    - `sandbox=False` to keep only the bytecode-based validation.
    - Configure `strict=False` to log name-check violations instead of raising or `enabled=False` to leave the function unchanged.
- `forbid_side_effects` instruments builtin operations that commonly mutate process state (e.g. file writes, subprocess
  launches) to surface accidental side effects.
    - Pass `strict=False` to warn and allow the attempted side effect or `enabled=False` to skip patching entirely.

## Future purity checks to explore

The current decorators focus on globals, determinism, and structural immutability.

Additional checks that build on the same inspection hooks could include:

- **Environment isolation** &mdash; raise when a function touches environment variables, current working directory, or
  other process-wide configuration through `os.environ`, `os.chdir`, or similar APIs.
- **I/O safelists** &mdash; expand the `forbid_side_effects` strategy with dedicated helpers that specifically deny
  file, socket, or HTTP operations unless a pure-safe allowlist is provided.
- **Mutable default detection** &mdash; detect functions whose default arguments or closed-over state are mutable so
  callers do not accidentally share state across invocations.
- **Dependency purity enforcement** &mdash; verify that functions only call other decorated or allowlisted pure functions
  by walking the bytecode or AST.

These ideas could live alongside the existing decorators as optional opt-in guards so projects can combine them to match
their definition of purity.

## Frequently asked questions

### Can these decorators be enabled globally, like `perl`'s `strict` pragma?

No. Python does not provide a hook that automatically wraps every function that is imported or defined after a module
loads. The decorators in this project operate by returning a new callable, so each target function (or method) has to be
wrapped explicitly. You can build your own helpers that iterate over a module or class and decorate selected callables,
but the library cannot apply itself universally without the caller opting in on a per-function basis.

## Side Effects

A side effect is any interaction with outside state other than computing and returning a value.

Canonical side effects and impurity sources:

_State mutation_: modifying globals, nonlocals, class/static attributes, singletons, caches, or the objects passed in as
arguments (in-place changes).

_I/O_: printing/logging, reading/writing files, networking, databases, stdin/stdout/stderr, GUI operations.

_Process/system effects_: spawning threads/processes, signals, timers, sleeping, exiting the process.

_Nondeterministic sources_: reading clocks (now, time), random/URNGs (random, secrets, uuid4, os.urandom), environment
variables, current working directory, locale.

_Hidden global dependencies_: reading mutable module state or configuration not provided as explicit parameters.

_Observable control effects:_ raising exceptions or relying on exceptions for normal control can be considered effects
in stricter definitions; total purity disallows them, weaker purity allows deterministic exceptions for invalid inputs.
