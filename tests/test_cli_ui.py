import pytest

from oeis_matcher import cli, web


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["ui"], {"host": "127.0.0.1", "port": 8766, "open_browser": True}),
        (
            ["ui", "--host", "localhost", "--port", "9876", "--no-browser"],
            {"host": "localhost", "port": 9876, "open_browser": False},
        ),
    ],
)
def test_ui_launcher(monkeypatch, argv, expected):
    calls = []
    monkeypatch.setattr(web, "serve", lambda **kwargs: calls.append(kwargs))

    assert cli.main(argv) == 0
    assert calls == [expected]


def test_ui_rejects_non_loopback_host():
    with pytest.raises(SystemExit):
        cli.main(["ui", "--host", "0.0.0.0"])
