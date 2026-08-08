"""Cursor movement math + action execution via pynput.

The acceleration curve is ported from tracky-mouse (MIT, (c) Isaiah
Odhner), https://github.com/1j01/tracky-mouse. It damps small movements
hard while leaving large ones fast, which stabilizes the cursor without an
averaging filter's latency -- each frame's output depends only on that
frame's input.

The pure math (`accelerate`, `clamp`) is separated from the pynput-driving
`MouseController` so it can be unit tested without a real display or OS
mouse.
"""
from __future__ import annotations

import math
import time
from typing import Callable

from pynput.mouse import Button, Controller

from .config import AppConfig

_ACTIONS = {
    "left_click": lambda m: m.click(Button.left, 1),
    "right_click": lambda m: m.click(Button.right, 1),
    "double_click": lambda m: m.click(Button.left, 2),
    "scroll_up": lambda m: m.scroll(0, 1),
    "scroll_down": lambda m: m.scroll(0, -1),
    "none": lambda m: None,
}

# OS cursor-position rounding tolerance: a divergence beyond this from the
# position this controller last wrote means something else -- the physical
# mouse -- moved the cursor.
YIELD_DETECT_PX = 2


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def accelerate(delta: float, acceleration: float) -> float:
    """Power curve: small movements shrink far more than large ones, so
    holding still is genuinely still and fine positioning is possible while
    big movements stay fast. `acceleration` of 0 is a linear pass-through."""
    return delta * (abs(delta * 5.0) ** acceleration)


class MouseController:
    def __init__(
        self,
        config: AppConfig,
        screen_size: tuple[int, int],
        mouse=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._screen_w, self._screen_h = screen_size
        self._mouse = mouse if mouse is not None else Controller()
        self._clock = clock
        self._cursor_x: float | None = None
        self._cursor_y: float | None = None
        self.yielded = False
        self._yield_started_at: float | None = None
        self._last_seen_x: float | None = None
        self._last_seen_y: float | None = None

    def update_config(self, config: AppConfig) -> None:
        self._config = config

    def reanchor(self) -> None:
        """Resyncs to the real OS cursor position, so a cursor moved by a
        physical mouse (while paused, or while yielded) is not fought."""
        cur_x, cur_y = self._mouse.position
        self._cursor_x = float(cur_x)
        self._cursor_y = float(cur_y)
        self._last_seen_x = float(cur_x)
        self._last_seen_y = float(cur_y)
        self.yielded = False
        self._yield_started_at = None

    def move_cursor(self, movement_x: float, movement_y: float) -> None:
        """Applies one frame of averaged point movement, in camera pixels."""
        if self._cursor_x is None:
            return  # not yet reanchored -- nothing to compare or move from

        cur_x, cur_y = self._mouse.position

        if self.yielded:
            self._update_yield_timer(cur_x, cur_y)
            return

        if (
            abs(cur_x - self._cursor_x) > YIELD_DETECT_PX
            or abs(cur_y - self._cursor_y) > YIELD_DETECT_PX
        ):
            # Something other than this controller moved the cursor -- the
            # physical mouse. Stop fighting it.
            self.yielded = True
            self._yield_started_at = self._clock()
            self._last_seen_x, self._last_seen_y = float(cur_x), float(cur_y)
            return

        if not (math.isfinite(movement_x) and math.isfinite(movement_y)):
            # clamp() would turn a NaN into the screen edge rather than
            # rejecting it, teleporting the cursor. Drop the frame instead.
            return

        cal = self._config.calibration
        delta_x = accelerate(movement_x * cal.sensitivity_x, cal.acceleration)
        delta_y = accelerate(movement_y * cal.sensitivity_y, cal.acceleration)

        # Threshold after the curve, so its unit is honestly "screen pixels
        # of cursor movement" rather than pixels before a curve is applied.
        if abs(delta_x * self._screen_w) < cal.motion_threshold_px:
            delta_x = 0.0
        if abs(delta_y * self._screen_h) < cal.motion_threshold_px:
            delta_y = 0.0

        # The tracked frame is already mirrored by FaceTracker.process, so
        # camera x matches screen x: the user's right is +x in both. (Upstream
        # tracky-mouse subtracts here because it tracks an unmirrored frame.)
        self._cursor_x = clamp(
            self._cursor_x + delta_x * self._screen_w, 0, self._screen_w - 1
        )
        self._cursor_y = clamp(
            self._cursor_y + delta_y * self._screen_h, 0, self._screen_h - 1
        )
        self._mouse.position = (int(self._cursor_x), int(self._cursor_y))

    def _update_yield_timer(self, cur_x: int, cur_y: int) -> None:
        if (
            abs(cur_x - self._last_seen_x) > YIELD_DETECT_PX
            or abs(cur_y - self._last_seen_y) > YIELD_DETECT_PX
        ):
            # Still moving -- keep pushing the resume deadline out.
            self._yield_started_at = self._clock()
        self._last_seen_x, self._last_seen_y = float(cur_x), float(cur_y)

        quiet_for = self._clock() - self._yield_started_at
        if quiet_for >= self._config.calibration.yield_resume_after_s:
            self.reanchor()

    def fire_action(self, gesture_name: str) -> None:
        action = self._config.gestures[gesture_name].action
        _ACTIONS[action](self._mouse)
