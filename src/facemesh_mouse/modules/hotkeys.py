"""Global hotkeys: toggle pause, reopen config window."""
from __future__ import annotations

from typing import Callable

from pynput import keyboard

TOGGLE_PAUSE_HOTKEY = "<ctrl>+<alt>+p"
OPEN_CONFIG_HOTKEY = "<ctrl>+<alt>+o"


class HotkeyListener:
    def __init__(
        self,
        on_toggle_pause: Callable[[], None],
        on_open_config: Callable[[], None],
    ) -> None:
        self._listener = keyboard.GlobalHotKeys(
            {
                TOGGLE_PAUSE_HOTKEY: on_toggle_pause,
                OPEN_CONFIG_HOTKEY: on_open_config,
            }
        )

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()
