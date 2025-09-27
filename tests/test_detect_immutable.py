import pytest
from pure_function_decorators import detect_immutable


@detect_immutable
def touch_list(a):
    a.append(3)
    return sum(a)


def test_mutation_detected():
    with pytest.raises(RuntimeError) as ei:
        touch_list([1, 2])
    assert "Argument mutated" in str(ei.value)


@detect_immutable
def pure(a):
    return tuple(sorted(a))


def test_no_mutation():
    assert pure({3, 1, 2}) == (1, 2, 3)
