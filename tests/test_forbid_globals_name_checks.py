import pytest
from pure_function_decorators import forbid_globals

CONST = 10
counter = 0


def test_rejects_at_decoration_time() -> None:
    with pytest.raises(RuntimeError):

        @forbid_globals(check_names=True, sandbox=False)
        def bad(x: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return x + CONST  # triggers


def test_allows_when_in_allow_list() -> None:
    @forbid_globals(allow=("CONST",), check_names=True, sandbox=False)
    def ok(x: int) -> int:
        return x + CONST

    assert ok(1) == 11


def test_works_without_parentheses() -> None:
    @forbid_globals
    def pure(x: int) -> int:
        return x * 2

    assert pure(3) == 6


def test_rejects_builtin_when_disabled() -> None:
    with pytest.raises(RuntimeError):

        @forbid_globals(allow_builtins=False, check_names=True, sandbox=False)
        def use_len(seq: list[int]) -> int:  # pyright: ignore[reportUnusedFunction]
            return len(seq)


def test_store_global_permitted_when_configured() -> None:
    global counter

    @forbid_globals(check_names=True, sandbox=False, include_store_delete=False)
    def increment_counter() -> int:
        global counter
        counter = 5
        return 5

    assert increment_counter() == 5
    assert counter == 5
    counter = 0


def test_import_detected_unless_disabled() -> None:
    with pytest.raises(RuntimeError):

        @forbid_globals(check_names=True, sandbox=False)
        def load_module() -> None:  # pyright: ignore[reportUnusedFunction]
            import math

            del math

    @forbid_globals(check_names=True, sandbox=False, include_imports=False)
    def load_module_ok() -> None:
        import math

        del math

    load_module_ok()


def test_check_names_strict_false_warns(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")

    @forbid_globals(check_names=True, sandbox=False, strict=False)
    def relaxed(x: int) -> int:
        return x + CONST

    assert relaxed(1) == 11
    assert any("Global names referenced" in message for message in caplog.messages)
