from pure_function_decorators.main import main
from pytest import CaptureFixture


def test_raise(capsys: CaptureFixture[str]) -> None:
    main()
    assert "Ritchie Blackmore" in capsys.readouterr().out
