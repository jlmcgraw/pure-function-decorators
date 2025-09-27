import pytest
from pure_function_decorators import forbid_global_names

CONST = 10


def test_rejects_at_decoration_time() -> None:
    with pytest.raises(RuntimeError):

        @forbid_global_names()
        def bad(x: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return x + CONST  # triggers


def test_allows_when_in_allow_list() -> None:
    @forbid_global_names(allow=("CONST",))
    def ok(x: int) -> int:
        return x + CONST

    assert ok(1) == 11


def test_works_without_parentheses() -> None:
    @forbid_global_names
    def pure(x: int) -> int:
        return x * 2

    assert pure(3) == 6
