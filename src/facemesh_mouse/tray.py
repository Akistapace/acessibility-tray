"""System tray icon: Pause/Resume, Open Config, Quit.

Icon color reflects one state, chosen by precedence (highest first): paused
overrides everything else the user might also be seeing (a face, a physical
mouse) since it's the state they explicitly asked for; yielded overrides
no-face and running.
"""
from __future__ import annotations

import threading
from typing import Callable

import pystray
from PIL import Image, ImageDraw


def _make_icon_image(color: str) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, size - 8, size - 8), fill=color)
    return img


_ICON_RUNNING = _make_icon_image("#2ecc71")
_ICON_PAUSED = _make_icon_image("#f1c40f")
_ICON_NO_FACE = _make_icon_image("#e67e22")
_ICON_YIELDED = _make_icon_image("#3498db")


class TrayIcon:
    def __init__(
        self,
        on_toggle_pause: Callable[[], bool],
        on_open_config: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_toggle_pause = on_toggle_pause
        self._on_open_config = on_open_config
        self._on_quit = on_quit
        self._paused = False
        self._no_face = False
        self._yielded = False
        self._icon = pystray.Icon(
            "facemesh_mouse",
            _ICON_RUNNING,
            "FaceMesh Mouse",
            menu=pystray.Menu(
                pystray.MenuItem(self._pause_label, self._toggle_pause),
                pystray.MenuItem("Reabrir Config", self._open_config, default=True),
                pystray.MenuItem("Sair", self._quit),
            ),
        )

    def _pause_label(self, _item) -> str:
        return "Retomar" if self._paused else "Pausar"

    def _toggle_pause(self, _icon=None, _item=None) -> None:
        self._paused = self._on_toggle_pause()
        self._refresh()
        self._icon.update_menu()

    def toggle_pause(self) -> None:
        """Public entry point for external callers (e.g. global hotkeys)."""
        self._toggle_pause()

    def _open_config(self, _icon=None, _item=None) -> None:
        self._on_open_config()

    def _quit(self, _icon=None, _item=None) -> None:
        self._on_quit()
        self._icon.stop()

    def set_no_face(self, no_face: bool) -> None:
        self._no_face = no_face
        self._refresh()

    def set_yielded(self, yielded: bool) -> None:
        """Called when cursor control is yielded to a physical mouse touch
        (see `MouseController.yielded`)."""
        self._yielded = yielded
        self._refresh()

    def _refresh(self) -> None:
        if self._paused:
            self._icon.icon = _ICON_PAUSED
        elif self._yielded:
            self._icon.icon = _ICON_YIELDED
        elif self._no_face:
            self._icon.icon = _ICON_NO_FACE
        else:
            self._icon.icon = _ICON_RUNNING

    def run_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._icon.stop()
