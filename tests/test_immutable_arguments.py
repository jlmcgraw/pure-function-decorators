from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest
from pure_function_decorators import immutable_arguments

if TYPE_CHECKING:
    from collections.abc import Iterable


@immutable_arguments
def touch_list(a: list[int]) -> int:
    a.append(3)
    return sum(a)


def test_mutation_detected() -> None:
    payload = [1, 2]
    with pytest.raises(RuntimeError) as ei:
        touch_list(payload)
    assert "Argument mutated" in str(ei.value)
    # The decorator deep-copies inputs so the caller's data remains untouched.
    assert payload == [1, 2]


@immutable_arguments
def pure(a: Iterable[int]) -> tuple[int, ...]:
    return tuple(sorted(a))


def test_no_mutation() -> None:
    assert pure({3, 1, 2}) == (1, 2, 3)


@immutable_arguments
def mutate_nested(data: dict[str, list[int]]) -> None:
    data["numbers"].append(99)


def test_reports_precise_path() -> None:
    with pytest.raises(RuntimeError) as ei:
        mutate_nested({"numbers": [1, 2, 3]})
    assert "arg[0]/['numbers']/<len>" in str(ei.value)


@immutable_arguments
def mutate_kwarg(*, payload: list[int]) -> None:
    payload.pop()


def test_kwargs_checked() -> None:
    with pytest.raises(RuntimeError) as ei:
        mutate_kwarg(payload=[1, 2, 3])
    assert "kwarg['payload']/<len>" in str(ei.value)


@dataclasses.dataclass
class Box:
    value: int


@immutable_arguments
def mutate_attribute(box: Box) -> None:
    box.value += 1


def test_detects_attribute_mutation() -> None:
    with pytest.raises(RuntimeError) as ei:
        mutate_attribute(Box(1))
    assert "arg[0]/.__dict__/['value']" in str(ei.value)


def test_warn_only_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")

    @immutable_arguments(warn_only=True)
    def mutate(data: list[int]) -> None:
        data.append(99)

    mutate([1, 2, 3])
    assert any("Argument mutated" in message for message in caplog.messages)


@dataclasses.dataclass
class Payload:
    numbers: list[int]


def test_warn_only_returns_mutated_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")

    @immutable_arguments(warn_only=True)
    def mutate_args(
        target: list[int], *, payload: Payload
    ) -> tuple[list[int], list[int]]:
        target.append(99)
        payload.numbers.append(42)
        return target, payload.numbers

    original = [1, 2, 3]
    payload = Payload(numbers=[4, 5])
    mutated_args, mutated_payload = mutate_args(original, payload=payload)

    assert original == [1, 2, 3]
    assert payload.numbers == [4, 5]
    assert mutated_args == [1, 2, 3, 99]
    assert mutated_payload == [4, 5, 42]
    assert any("Argument mutated" in message for message in caplog.messages)


def test_strict_false_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")

    @immutable_arguments(strict=False)
    def mutate(data: list[int]) -> list[int]:
        data.append(5)
        return data

    original = [1, 2]
    result = mutate(original)

    assert original == [1, 2]
    assert result == [1, 2, 5]
    assert any("Argument mutated" in message for message in caplog.messages)


def test_enabled_false_disables_checks() -> None:
    @immutable_arguments(enabled=False)
    def mutate(data: list[int]) -> list[int]:
        data.append(7)
        return data

    payload = [1, 2]
    result = mutate(payload)

    assert payload == [1, 2, 7]
    assert result is payload
