import pytest
from pure_function_decorators import forbid_globals

CONST = 5


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
