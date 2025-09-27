from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from pure_function_decorators import enforce_immutable

if TYPE_CHECKING:
    from collections.abc import Iterable


@enforce_immutable
def touch_list(a: list[int]) -> int:
    a.append(3)
    return sum(a)


def test_mutation_prevented() -> None:
    test_list = [1, 2, 3]
    touch_list(test_list)
    assert test_list == [1, 2, 3]


@enforce_immutable
def pure(a: Iterable[int]) -> tuple[int, ...]:
    return tuple(sorted(a))


def test_no_mutation() -> None:
    assert pure({3, 1, 2}) == (1, 2, 3)


@dataclasses.dataclass
class Payload:
    numbers: list[int]


@enforce_immutable
def mutate_args(target: list[int], *, payload: Payload) -> tuple[list[int], list[int]]:
    target.append(99)
    payload.numbers.append(42)
    return target, payload.numbers


def test_args_and_kwargs_are_copied() -> None:
    original = [1, 2, 3]
    payload = Payload(numbers=[4, 5])
    mutated_args, mutated_payload = mutate_args(original, payload=payload)
    assert original == [1, 2, 3]
    assert payload.numbers == [4, 5]
    # The function still observes the mutated versions internally.
    assert mutated_args == [1, 2, 3, 99]
    assert mutated_payload == [4, 5, 42]
