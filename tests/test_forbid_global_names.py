import pytest
from pure_function_decorators import forbid_global_names

CONST = 10


def test_rejects_at_decoration_time():
    with pytest.raises(RuntimeError):

        @forbid_global_names()
        def bad(x):
            return x + CONST  # triggers


def test_allows_when_in_allow_list():
    @forbid_global_names(allow=("CONST",))
    def ok(x):
        return x + CONST

    assert ok(1) == 11


def test_works_without_parentheses():
    @forbid_global_names
    def pure(x):
        return x * 2

    assert pure(3) == 6
