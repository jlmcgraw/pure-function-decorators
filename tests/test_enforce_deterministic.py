from __future__ import annotations

import asyncio
import pickle
import threading

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


@enforce_deterministic
async def async_add(x: int, y: int) -> int:
    await asyncio.sleep(0)
    return x + y


def test_async_deterministic_values_allowed() -> None:
    async def runner() -> None:
        first, second = await asyncio.gather(async_add(2, 3), async_add(2, 3))
        assert first == second == 5

    asyncio.run(runner())


async_state = {"value": 0}


@enforce_deterministic
async def async_bump() -> int:
    async_state["value"] += 1
    await asyncio.sleep(0)
    return async_state["value"]


def test_async_nondeterministic_values_rejected() -> None:
    async def runner() -> None:
        assert await async_bump() == 1
        with pytest.raises(ValueError):
            await async_bump()

    asyncio.run(runner())
    async_state["value"] = 0


@enforce_deterministic
def thread_safe_add(x: int, y: int) -> int:
    return x + y


def test_threaded_deterministic_values_allowed() -> None:
    results: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(thread_safe_add(4, 5))
        except BaseException as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert results == [9] * 10


def test_threaded_nondeterministic_values_rejected() -> None:
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    results: list[int] = []

    @enforce_deterministic
    def thread_identity() -> int:
        barrier.wait()
        return threading.get_ident()

    def worker() -> None:
        try:
            results.append(thread_identity())
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert any(isinstance(err, ValueError) for err in errors)
    assert len(results) + len(errors) == 2


def test_strict_false_warns(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")
    counter = {"value": 0}

    @enforce_deterministic(strict=False)
    def relaxed_bump() -> int:
        counter["value"] += 1
        return counter["value"]

    assert relaxed_bump() == 1
    assert relaxed_bump() == 2
    assert any(
        "Non-deterministic output detected" in message for message in caplog.messages
    )


def test_enabled_false_skips_checks() -> None:
    state = {"value": 0}

    @enforce_deterministic(enabled=False)
    def bump_without_checks() -> int:
        state["value"] += 1
        return state["value"]

    assert bump_without_checks() == 1
    assert bump_without_checks() == 2
