from __future__ import annotations

import pickle

import pytest
from pure_function_decorators import enforce_deterministic


@enforce_deterministic
def add(x: int, y: int) -> int:
    return x + y


def test_deterministic_values_allowed() -> None:
    assert add(1, 2) == 3
    assert add(x=1, y=2) == 3


state = {"value": 0}


@enforce_deterministic
def bump() -> int:
    state["value"] += 1
    return state["value"]


def test_nondeterministic_values_rejected() -> None:
    assert bump() == 1
    with pytest.raises(ValueError):
        bump()
    state["value"] = 0


@enforce_deterministic
def make_list(n: int) -> list[int]:
    return list(range(n))


def test_unhashable_but_equal_results_cached() -> None:
    assert make_list(3) == [0, 1, 2]
    assert make_list(3) == [0, 1, 2]


@enforce_deterministic
def echo(obj: object) -> object:
    return obj


def test_unpickleable_arguments_raise() -> None:
    with pytest.raises((pickle.PicklingError, AttributeError, TypeError)):
        echo(lambda: None)
