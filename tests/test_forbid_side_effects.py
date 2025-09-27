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


@forbid_side_effects
def do_time() -> float:
    import time

    return time.time()


def test_time_blocked() -> None:
    with pytest.raises(RuntimeError):
        do_time()


@forbid_side_effects
def read_env() -> str:
    import os

    return os.environ["HOME"]


def test_environ_blocked() -> None:
    with pytest.raises(RuntimeError):
        read_env()


@forbid_side_effects
def send_warning() -> None:
    import warnings

    warnings.warn("nope")


def test_warnings_blocked() -> None:
    with pytest.raises(RuntimeError):
        send_warning()


@forbid_side_effects
def start_thread() -> None:
    import threading

    threading.Thread(target=lambda: None).start()


def test_thread_start_blocked() -> None:
    with pytest.raises(RuntimeError):
        start_thread()


@forbid_side_effects
def pure_function(x: int, y: int) -> int:
    return x + y


def test_pure_function_succeeds() -> None:
    # The decorator should not interfere with side-effect-free code and must
    # restore the patched globals afterwards so ``print`` works as normal.
    assert pure_function(2, 3) == 5
    print("side effects restored")
