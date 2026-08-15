from unittest.mock import MagicMock

from pynput.keyboard import Key

from facemesh_mouse import voice_typing


def test_toggle_voice_typing_sends_win_h(monkeypatch):
    controller_mock = MagicMock()
    monkeypatch.setattr(voice_typing, "Controller", lambda: controller_mock)

    voice_typing.toggle_voice_typing()

    controller_mock.press.assert_any_call(Key.cmd)
    controller_mock.press.assert_any_call("h")
    controller_mock.release.assert_any_call("h")
    controller_mock.release.assert_any_call(Key.cmd)


def test_toggle_voice_typing_releases_cmd_even_if_pressing_h_fails(monkeypatch):
    """A stuck-down Windows key would hijack every subsequent keystroke
    system-wide -- worse than the dictation flyout simply not opening."""
    controller_mock = MagicMock()
    controller_mock.press.side_effect = [None, RuntimeError("simulated 'h' press failure")]
    monkeypatch.setattr(voice_typing, "Controller", lambda: controller_mock)

    voice_typing.toggle_voice_typing()  # must not raise

    controller_mock.release.assert_any_call(Key.cmd)


def test_toggle_voice_typing_survives_a_launch_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        voice_typing, "Controller", MagicMock(side_effect=RuntimeError("simulated failure"))
    )

    voice_typing.toggle_voice_typing()  # must not raise

    assert "voice typing" in capsys.readouterr().out
