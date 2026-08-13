from unittest.mock import MagicMock

from facemesh_mouse import virtual_keyboard


def test_open_virtual_keyboard_launches_osk(monkeypatch):
    popen_mock = MagicMock()
    monkeypatch.setattr(virtual_keyboard.subprocess, "Popen", popen_mock)

    virtual_keyboard.open_virtual_keyboard()

    popen_mock.assert_called_once_with(["osk.exe"])


def test_open_virtual_keyboard_survives_a_launch_failure(monkeypatch, capsys):
    """A missing/blocked osk.exe must never crash the caller -- the tray
    thread or the Tk event loop, depending on which entry point calls it."""

    def _boom(*_args, **_kwargs):
        raise FileNotFoundError("simulated osk.exe launch failure")

    monkeypatch.setattr(virtual_keyboard.subprocess, "Popen", _boom)

    virtual_keyboard.open_virtual_keyboard()  # must not raise

    assert "osk.exe" in capsys.readouterr().out
