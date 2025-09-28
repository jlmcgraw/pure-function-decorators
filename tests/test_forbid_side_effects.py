import os
import random
import sys
import time
from pathlib import Path
from typing import cast

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

    warnings.warn("nope", stacklevel=2)


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


@forbid_side_effects(strict=False)
def relaxed_print() -> int:
    print("relaxed")
    return 42


def test_strict_false_warns_and_allows(capfd: pytest.CaptureFixture[str]) -> None:
    assert relaxed_print() == 42
    captured = capfd.readouterr()
    assert "relaxed" in captured.out
    assert "Side effect blocked" in captured.err


@forbid_side_effects(enabled=False)
def allowed_print() -> None:
    print("allowed")


def test_enabled_false_does_not_patch(capfd: pytest.CaptureFixture[str]) -> None:
    allowed_print()
    captured = capfd.readouterr()
    assert captured.out == "allowed\n"
    assert "Side effect blocked" not in captured.err


def test_environ_get_blocked() -> None:
    @forbid_side_effects
    def read_with_get() -> str | None:
        return os.environ.get("HOME")

    with pytest.raises(RuntimeError):
        read_with_get()


def test_relaxed_std_streams_support_flush_and_attributes(
    capfd: pytest.CaptureFixture[str],
) -> None:
    @forbid_side_effects(strict=False)
    def flush_and_inspect() -> str | None:
        print("hello", flush=True)
        return sys.stdout.encoding

    encoding = flush_and_inspect()
    captured = capfd.readouterr()
    assert captured.out == "hello\n"
    assert "Side effect blocked: stdio write" in captured.err
    # ``encoding`` can legitimately be ``None`` (e.g. when stdout is binary),
    # but accessing it should not raise while the decorator is active.
    assert encoding is None or isinstance(encoding, str)


def test_relaxed_random_and_time_call_originals(
    capfd: pytest.CaptureFixture[str],
) -> None:
    @forbid_side_effects(strict=False)
    def use_random_and_sleep() -> float:
        value = random.random()
        time.sleep(0)
        return value

    result = use_random_and_sleep()
    captured = capfd.readouterr()
    assert 0.0 <= result < 1.0
    assert "Side effect blocked: random.random" in captured.err
    assert "Side effect blocked: time.sleep" in captured.err


def test_relaxed_environ_operations_warn() -> None:
    sentinel = object()
    key = "PFD_TEST_VAR"
    original = os.environ.get(key, sentinel)
    baseline_length = len(os.environ)

    @forbid_side_effects(strict=False)
    def mutate_env() -> tuple[int, bool]:
        os.environ[key] = "value"
        length = len(os.environ)
        present = any(candidate == key for candidate in os.environ)
        assert os.environ[key] == "value"
        del os.environ[key]
        return length, present

    try:
        length, present = mutate_env()
        # The proxy should forward len/iteration to the underlying mapping.
        assert length == baseline_length + 1
        assert present is True
        assert len(os.environ) == baseline_length
    finally:
        if original is sentinel:
            os.environ.pop(key, None)
        else:
            os.environ[key] = cast("str", original)
