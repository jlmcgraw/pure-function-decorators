from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest
from pure_function_decorators import detect_immutable

if TYPE_CHECKING:
    from collections.abc import Iterable


@detect_immutable
def touch_list(a: list[int]) -> int:
    a.append(3)
    return sum(a)


def test_mutation_detected() -> None:
    with pytest.raises(RuntimeError) as ei:
        touch_list([1, 2])
    assert "Argument mutated" in str(ei.value)


@detect_immutable
def pure(a: Iterable[int]) -> tuple[int, ...]:
    return tuple(sorted(a))


def test_no_mutation() -> None:
    assert pure({3, 1, 2}) == (1, 2, 3)


@detect_immutable
def mutate_nested(data: dict[str, list[int]]) -> None:
    data["numbers"].append(99)


def test_reports_precise_path() -> None:
    with pytest.raises(RuntimeError) as ei:
        mutate_nested({"numbers": [1, 2, 3]})
    assert "arg[0]/['numbers']/<len>" in str(ei.value)


@detect_immutable
def mutate_kwarg(*, payload: list[int]) -> None:
    payload.pop()


def test_kwargs_checked() -> None:
    with pytest.raises(RuntimeError) as ei:
        mutate_kwarg(payload=[1, 2, 3])
    assert "kwarg['payload']/<len>" in str(ei.value)


@dataclasses.dataclass
class Box:
    value: int


@detect_immutable
def mutate_attribute(box: Box) -> None:
    box.value += 1


def test_detects_attribute_mutation() -> None:
    with pytest.raises(RuntimeError) as ei:
        mutate_attribute(Box(1))
    assert "arg[0]/.__dict__/['value']" in str(ei.value)
