from pathlib import Path

import pytest
from pure_function_decorators import forbid_side_effects


@forbid_side_effects
def do_print() -> None:
    print("x")


def test_print_blocked() -> None:
    with pytest.raises(RuntimeError):
        do_print()


@forbid_side_effects
def do_open(tmp_path: Path) -> None:
    with open(tmp_path / "f.txt", "w") as handle:
        handle.write("x")


def test_open_blocked(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        do_open(tmp_path)


@forbid_side_effects
def do_random() -> float:
    import random

    return random.random()


def test_random_blocked() -> None:
    with pytest.raises(RuntimeError):
        do_random()
