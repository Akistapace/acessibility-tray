"""Toggles Windows' built-in voice typing (dictation).

The app doesn't build its own speech-to-text -- Windows already ships one,
offline-capable, that types recognized speech straight into whatever field
has focus. It's normally reached by the Win+H shortcut, which this app's
users can't press themselves (that's the reason the app exists), so this
module triggers it the same way the floating keyboard button opens the
touch keyboard -- from a click, via synthetic input -- rather than asking
for a keystroke the user can't make.
"""
from __future__ import annotations

from pynput.keyboard import Controller, Key


def toggle_voice_typing() -> None:
    """Sends Win+H, which starts (or stops, if already listening) Windows'
    voice typing flyout on whatever text field currently has focus.

    A failure here must never crash tracking, the tray, or the config
    window -- it's caught and printed, not raised.
    """
    try:
        keyboard = Controller()
        keyboard.press(Key.cmd)
        try:
            keyboard.press("h")
            keyboard.release("h")
        finally:
            keyboard.release(Key.cmd)
    except Exception as exc:  # noqa: BLE001 - a missing dictation must never crash tracking
        print(f"facemesh-mouse: could not toggle voice typing ({exc!r})")
