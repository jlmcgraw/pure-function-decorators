import pytest
from pure_function_decorators import forbid_global_names

CONST = 10
COUNTER = 0


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


def test_rejects_builtin_when_disabled() -> None:
    with pytest.raises(RuntimeError):

        @forbid_global_names(allow_builtins=False)
        def use_len(seq: list[int]) -> int:  # pyright: ignore[reportUnusedFunction]
            return len(seq)


def test_store_global_permitted_when_configured() -> None:
    global COUNTER

    @forbid_global_names(include_store_delete=False)
    def increment_counter() -> int:
        global COUNTER
        COUNTER = 5
        return 5

    assert increment_counter() == 5
    assert COUNTER == 5
    COUNTER = 0


def test_import_detected_unless_disabled() -> None:
    with pytest.raises(RuntimeError):

        @forbid_global_names()
        def load_module() -> None:  # pyright: ignore[reportUnusedFunction]
            import math  # noqa: F401

    @forbid_global_names(include_imports=False)
    def load_module_ok() -> None:
        import math  # noqa: F401

    load_module_ok()
