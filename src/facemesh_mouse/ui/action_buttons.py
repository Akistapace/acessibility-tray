"""A floating, draggable, always-on-top pair of circles -- keyboard and
mic -- that open the touch keyboard / toggle voice typing on click.

Grouped into one window (one drag moves both) rather than two independently
positioned buttons: two floating targets drifting apart over repeated drags
made them harder to find than a single pair that always stays together.

Stays alive for the whole app process -- constructed once in main.py, never
shown/hidden with the config window or pause state. Uses the same
`-transparentcolor` trick as click_feedback.py to render circles instead of
a rectangular window, but -- unlike the click-feedback pulse -- is never
click-through: it has to receive the drag and click events itself.
"""
from __future__ import annotations

import ctypes
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from . import click_feedback
from .. import voice_typing
from .. import virtual_keyboard
from ..modules import config as config_mod
from ..modules.config import AppConfig
from ..modules.mouse_controller import clamp

# A release within this many pixels of the press point, on both axes, is a
# click; past it on either axis, it's a drag. Matches the scale of
# DWELL_STILL_PX/YIELD_DETECT_PX elsewhere in this codebase.
CLICK_DRAG_THRESHOLD_PX = 5

SIZE = 60  # each circle's diameter, px
GAP = 6  # px between the two circles
WIDTH = SIZE * 2 + GAP
MARGIN = 24  # gap from the screen edge for the default corner position

KEYBOARD_COLOR = "#4da3ff"
MIC_COLOR = "#ff6b6b"
KEYBOARD_GLYPH = "⌨"
MIC_GLYPH = "🎤"

# Shown instead of the normal click pulse when the touch keyboard silently
# declines to open -- most commonly because no editable text field has
# focus (see virtual_keyboard.open_virtual_keyboard's docstring).
WARNING_PULSE_COLOR = "#ff4d4d"
NO_FOCUS_TOOLTIP_TEXT = "Clique num campo de texto antes de abrir o teclado"

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000

_SPI_GETWORKAREA = 0x0030


def _taskbar_reserved_px(screen_h: float) -> float:
    """How many pixels the taskbar currently reserves at the bottom of the
    screen (0 if it's auto-hidden or the query fails) -- used so the
    buttons' default corner sits above it instead of half-hidden behind
    it. `winfo_screenheight()` returns the full physical screen height,
    which includes that reserved strip."""
    work_area = wintypes.RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0):
        return 0.0
    return max(0.0, screen_h - work_area.bottom)


def _prevent_activation(window: tk.Toplevel) -> None:
    """Keeps clicking this window from stealing OS focus/activation from
    whatever the user had focused. Voice typing (unlike the touch keyboard)
    types wherever the real OS keyboard caret currently is -- if the click
    that opens it also focuses this window, the transcribed text has no
    field to land in."""
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, styles | WS_EX_NOACTIVATE)


def default_position(
    screen_w: float, screen_h: float, taskbar_reserved_px: float = 0
) -> tuple[float, float]:
    """Top-left corner for the group's default bottom-right placement, kept
    clear of the taskbar via `taskbar_reserved_px` (see
    `_taskbar_reserved_px`; 0 -- the default -- matches a screen with no
    taskbar reservation, e.g. in tests)."""
    return screen_w - WIDTH - MARGIN, screen_h - SIZE - MARGIN - taskbar_reserved_px


def resolve_position(
    saved_x: float | None,
    saved_y: float | None,
    screen_w: float,
    screen_h: float,
    taskbar_reserved_px: float = 0,
) -> tuple[float, float]:
    """Uses the saved position if there is one and it still fits the
    current screen; falls back to the default corner otherwise (e.g. no
    position was ever saved, or the resolution changed since it was)."""
    if saved_x is None or saved_y is None:
        return default_position(screen_w, screen_h, taskbar_reserved_px)
    if not (0 <= saved_x <= screen_w - WIDTH) or not (0 <= saved_y <= screen_h - SIZE):
        return default_position(screen_w, screen_h, taskbar_reserved_px)
    return saved_x, saved_y


def is_click(press: tuple[float, float], release: tuple[float, float]) -> bool:
    """A release within CLICK_DRAG_THRESHOLD_PX of the press point, on both
    axes, counts as a click rather than a drag -- forgiving of the small
    wobble a shaky press-and-release can have."""
    return (
        abs(release[0] - press[0]) <= CLICK_DRAG_THRESHOLD_PX
        and abs(release[1] - press[1]) <= CLICK_DRAG_THRESHOLD_PX
    )


class ActionButtons:
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
        self._press_local_x: float | None = None
        self._window_start: tuple[int, int] | None = None

        x, y = resolve_position(
            config.action_buttons.x,
            config.action_buttons.y,
            self._screen_w,
            self._screen_h,
            _taskbar_reserved_px(self._screen_h),
        )

        self._window = tk.Toplevel(parent)
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.attributes("-transparentcolor", "black")
        self._window.configure(bg="black")
        self._window.geometry(f"{WIDTH}x{SIZE}+{int(x)}+{int(y)}")

        canvas = tk.Canvas(self._window, width=WIDTH, height=SIZE, bg="black", highlightthickness=0)
        canvas.pack()
        canvas.create_oval(2, 2, SIZE - 2, SIZE - 2, fill=KEYBOARD_COLOR, outline="")
        canvas.create_text(SIZE / 2, SIZE / 2, text=KEYBOARD_GLYPH, fill="white", font=("Segoe UI", 20))
        mic_left = SIZE + GAP
        canvas.create_oval(mic_left + 2, 2, mic_left + SIZE - 2, SIZE - 2, fill=MIC_COLOR, outline="")
        canvas.create_text(
            mic_left + SIZE / 2, SIZE / 2, text=MIC_GLYPH, fill="white", font=("Segoe UI", 20)
        )

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_motion)
        canvas.bind("<ButtonRelease-1>", self._on_release)

        self._window.update_idletasks()
        _prevent_activation(self._window)

    def _on_press(self, event) -> None:
        self._press_root = (event.x_root, event.y_root)
        self._press_local_x = event.x
        self._window_start = (self._window.winfo_x(), self._window.winfo_y())

    def _on_motion(self, event) -> None:
        if self._press_root is None or self._window_start is None:
            return
        dx = event.x_root - self._press_root[0]
        dy = event.y_root - self._press_root[1]
        new_x = clamp(self._window_start[0] + dx, 0, self._screen_w - WIDTH)
        new_y = clamp(self._window_start[1] + dy, 0, self._screen_h - SIZE)
        self._window.geometry(f"+{int(new_x)}+{int(new_y)}")
        self._window.update_idletasks()

    def _on_release(self, event) -> None:
        if self._press_root is None:
            return
        if is_click(self._press_root, (event.x_root, event.y_root)):
            if self._press_local_x is not None and self._press_local_x < SIZE:
                opened = virtual_keyboard.open_virtual_keyboard()
                if opened:
                    click_feedback.show_pulse(self._window, event.x_root, event.y_root)
                else:
                    click_feedback.show_pulse(
                        self._window, event.x_root, event.y_root, WARNING_PULSE_COLOR
                    )
                    click_feedback.show_tooltip(
                        self._window, event.x_root, event.y_root, NO_FOCUS_TOOLTIP_TEXT
                    )
            else:
                voice_typing.toggle_voice_typing()
                click_feedback.show_pulse(self._window, event.x_root, event.y_root)
        else:
            self._save_position(float(self._window.winfo_x()), float(self._window.winfo_y()))
        self._press_root = None
        self._press_local_x = None
        self._window_start = None

    def _save_position(self, x: float, y: float) -> None:
        # Keep the in-memory object in sync too -- ConfigWindow reads this
        # field fresh at its own save time (see config_gui.py).
        self._config.action_buttons.x = x
        self._config.action_buttons.y = y
        # Never write self._config's calibration/gestures back to disk:
        # main.py's copy of it goes stale the moment the user saves via the
        # config window (that flow only updates ConfigWindow's own deep
        # copy and the engine's config, never this object), so a whole-
        # object write here would silently revert the user's settings.
        # Read-modify-write against the file itself instead.
        try:
            on_disk = config_mod.load_config(self._config_path)
            on_disk.action_buttons.x = x
            on_disk.action_buttons.y = y
            config_mod.save_config(self._config_path, on_disk)
        except Exception as exc:  # noqa: BLE001 - a failed save must never crash the drag handler
            print(f"facemesh-mouse: could not save action buttons position ({exc!r})")

    def reset_position(self) -> None:
        """Moves the group back to its default corner, live, and persists
        it -- called from the config window's reset button."""
        x, y = default_position(self._screen_w, self._screen_h, _taskbar_reserved_px(self._screen_h))
        self._window.geometry(f"+{int(x)}+{int(y)}")
        self._save_position(x, y)

    def destroy(self) -> None:
        self._window.destroy()
