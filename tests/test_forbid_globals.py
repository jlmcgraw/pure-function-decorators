import asyncio

import pytest
from pure_function_decorators import forbid_globals

CONST = 5
STATE = {"value": 0}


@forbid_globals()
def uses_const(x: int) -> int:
    return x + CONST  # blocked unless whitelisted


def test_globals_blocked() -> None:
    with pytest.raises(NameError):
        uses_const(1)


@forbid_globals(allow=("CONST",))
def uses_const_ok(x: int) -> int:
    return x + CONST


def test_globals_allowed() -> None:
    assert uses_const_ok(2) == 7


@forbid_globals()
def mutate_global_state() -> None:
    STATE["value"] = 99


def test_globals_restored_even_after_mutation() -> None:
    with pytest.raises(NameError):
        mutate_global_state()
    # The mutation performed during the call is discarded when globals are restored.
    assert STATE == {"value": 0}


@forbid_globals(allow=("STATE",))
def mutate_allowed() -> None:
    STATE["value"] = 100


def test_allowed_globals_persist() -> None:
    mutate_allowed()
    assert STATE == {"value": 100}
    STATE["value"] = 0


@forbid_globals()
async def async_uses_const(x: int) -> int:
    return x + CONST


def test_async_globals_blocked() -> None:
    async def runner() -> None:
        with pytest.raises(NameError):
            await async_uses_const(1)

    asyncio.run(runner())


@forbid_globals(allow=("CONST",))
async def async_uses_const_ok(x: int) -> int:
    return x + CONST


def test_async_globals_allowed() -> None:
    async def runner() -> None:
        assert await async_uses_const_ok(3) == 8

    asyncio.run(runner())


@forbid_globals(enabled=False)
def relaxed(x: int) -> int:
    return x + CONST


def test_enabled_false_leaves_function_untouched() -> None:
    assert relaxed(4) == 9
