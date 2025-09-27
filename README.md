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
from pure-function-decorators import (
    enforce_deterministic,
    enforce_immutable,
    forbid_global_names,
    forbid_globals,
    forbid_side_effects,
)


@forbid_global_names()
def bad(x):
    return x + CONST  

CONST = 10
bad(1)   # Raises RuntimeError
```

## Documentation

The complete documentation can be found at the
[pure-function-decorators home page](https://jlmcgraw.github.io/pure-function-decorators)
