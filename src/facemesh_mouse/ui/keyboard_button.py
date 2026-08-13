"""A floating, draggable, always-on-top circle that opens Windows' virtual
keyboard on click.

Stays alive for the whole app process -- constructed once in main.py,
never shown/hidden with the config window or pause state. Uses the same
`-transparentcolor` trick as click_feedback.py to render a circle instead
of a rectangular window, but -- unlike the click-feedback pulse -- is never
click-through: it has to receive the drag and click events itself.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from .. import virtual_keyboard
from ..modules import config as config_mod
from ..modules.config import AppConfig
from ..modules.mouse_controller import clamp

# A release within this many pixels of the press point, on both axes, is a
# click; past it on either axis, it's a drag. Matches the scale of
# DWELL_STILL_PX/YIELD_DETECT_PX elsewhere in this codebase.
CLICK_DRAG_THRESHOLD_PX = 5

SIZE = 60  # circle diameter, px
MARGIN = 24  # gap from the screen edge for the default corner position
ACCENT_COLOR = "#4da3ff"  # same blue as click_feedback's pulse ring
GLYPH = "⌨"  # "⌨"


def default_position(screen_w: float, screen_h: float) -> tuple[float, float]:
    """Top-left corner for the button's default bottom-right placement."""
    return screen_w - SIZE - MARGIN, screen_h - SIZE - MARGIN


def resolve_position(
    saved_x: float | None, saved_y: float | None, screen_w: float, screen_h: float
) -> tuple[float, float]:
    """Uses the saved position if there is one and it still fits the
    current screen; falls back to the default corner otherwise (e.g. no
    position was ever saved, or the resolution changed since it was)."""
    if saved_x is None or saved_y is None:
        return default_position(screen_w, screen_h)
    if not (0 <= saved_x <= screen_w - SIZE) or not (0 <= saved_y <= screen_h - SIZE):
        return default_position(screen_w, screen_h)
    return saved_x, saved_y


def is_click(press: tuple[float, float], release: tuple[float, float]) -> bool:
    """A release within CLICK_DRAG_THRESHOLD_PX of the press point, on both
    axes, counts as a click rather than a drag -- forgiving of the small
    wobble a shaky press-and-release can have."""
    return (
        abs(release[0] - press[0]) <= CLICK_DRAG_THRESHOLD_PX
        and abs(release[1] - press[1]) <= CLICK_DRAG_THRESHOLD_PX
    )


class KeyboardButton:
    def __init__(
        self,
        parent: tk.Misc,
        config: AppConfig,
        config_path: str | Path,
        screen_size: tuple[int, int],
    ) -> None:
        self._config = config
        self._config_path = config_path
        self._screen_w, self._screen_h = screen_size
        self._press_root: tuple[float, float] | None = None
        self._window_start: tuple[int, int] | None = None

        x, y = resolve_position(
            config.keyboard_button.x, config.keyboard_button.y, self._screen_w, self._screen_h
        )

        self._window = tk.Toplevel(parent)
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.attributes("-transparentcolor", "black")
        self._window.configure(bg="black")
        self._window.geometry(f"{SIZE}x{SIZE}+{int(x)}+{int(y)}")

        canvas = tk.Canvas(self._window, width=SIZE, height=SIZE, bg="black", highlightthickness=0)
        canvas.pack()
        canvas.create_oval(2, 2, SIZE - 2, SIZE - 2, fill=ACCENT_COLOR, outline="")
        canvas.create_text(SIZE / 2, SIZE / 2, text=GLYPH, fill="white", font=("Segoe UI", 20))

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_motion)
        canvas.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event) -> None:
        self._press_root = (event.x_root, event.y_root)
        self._window_start = (self._window.winfo_x(), self._window.winfo_y())

    def _on_motion(self, event) -> None:
        if self._press_root is None or self._window_start is None:
            return
        dx = event.x_root - self._press_root[0]
        dy = event.y_root - self._press_root[1]
        new_x = clamp(self._window_start[0] + dx, 0, self._screen_w - SIZE)
        new_y = clamp(self._window_start[1] + dy, 0, self._screen_h - SIZE)
        self._window.geometry(f"+{int(new_x)}+{int(new_y)}")
        self._window.update_idletasks()

    def _on_release(self, event) -> None:
        if self._press_root is None:
            return
        if is_click(self._press_root, (event.x_root, event.y_root)):
            virtual_keyboard.open_virtual_keyboard()
        else:
            self._config.keyboard_button.x = float(self._window.winfo_x())
            self._config.keyboard_button.y = float(self._window.winfo_y())
            config_mod.save_config(self._config_path, self._config)
        self._press_root = None
        self._window_start = None

    def destroy(self) -> None:
        self._window.destroy()
