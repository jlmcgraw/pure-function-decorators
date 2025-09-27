import pytest
from pure_function_decorators import forbid_side_effects


@forbid_side_effects
def do_print():
    print("x")


def test_print_blocked():
    with pytest.raises(RuntimeError):
        do_print()


@forbid_side_effects
def do_open(tmp_path):
    open(tmp_path / "f.txt", "w")  # type: ignore[arg-type]


def test_open_blocked(tmp_path):
    with pytest.raises(RuntimeError):
        do_open(tmp_path)


@forbid_side_effects
def do_random():
    import random

    return random.random()


def test_random_blocked():
    with pytest.raises(RuntimeError):
        do_random()
