"""Cursor movement math + action execution via pynput.

The acceleration curve damps small movements hard while leaving large ones
fast, which stabilizes the cursor without an averaging filter's latency --
each frame's output depends only on that frame's input.

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

# Cursor-position tolerance for "holding still" while dwell-clicking.
DWELL_STILL_PX = 3


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# Below this magnitude (post-sensitivity, pre-acceleration) the curve
# shrinks the delta; above it, the curve grows the delta. Derived from
# measuring real head-tracking output at the default sensitivity: holding
# still produces deltas around 0.02-0.03, deliberate movement produces
# 0.15+, so 0.05 cleanly separates the two.
_ACCELERATION_REFERENCE = 0.05


def accelerate(delta: float, acceleration: float, reference: float = _ACCELERATION_REFERENCE) -> float:
    """Power curve: below `reference` magnitude the delta shrinks (fine
    positioning), above it the delta grows (fast travel), so holding still
    is genuinely still while big movements stay fast. `acceleration` of 0
    is a linear pass-through (the curve's gain is 1 everywhere)."""
    magnitude = abs(delta)
    if magnitude < 1e-9:
        return 0.0
    gain = (magnitude / reference) ** acceleration
    return delta * gain


class MouseController:
    def __init__(
        self,
        config: AppConfig,
        screen_size: tuple[int, int],
        mouse=None,
        clock: Callable[[], float] = time.monotonic,
        on_action: Callable[[str, str, tuple[int, int]], None] | None = None,
    ) -> None:
        self._config = config
        self._screen_w, self._screen_h = screen_size
        self._mouse = mouse if mouse is not None else Controller()
        self._clock = clock
        self._on_action = on_action
        self._cursor_x: float | None = None
        self._cursor_y: float | None = None
        self.yielded = False
        self._yield_started_at: float | None = None
        self._last_seen_x: float | None = None
        self._last_seen_y: float | None = None
        self._dwell_anchor_x: float | None = None
        self._dwell_anchor_y: float | None = None
        self._dwell_started_at: float | None = None
        self._dwell_fired = False

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
        # A stale dwell timer from before the transition (e.g. time spent
        # paused) must not carry over -- it would fire a click the instant
        # control resumes, on a target the user never dwelled on.
        self._dwell_anchor_x = None
        self._dwell_anchor_y = None
        self._dwell_fired = False

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
        # camera x matches screen x: the user's right is +x in both.
        self._cursor_x = clamp(
            self._cursor_x + delta_x * self._screen_w, 0, self._screen_w - 1
        )
        self._cursor_y = clamp(
            self._cursor_y + delta_y * self._screen_h, 0, self._screen_h - 1
        )
        self._mouse.position = (int(self._cursor_x), int(self._cursor_y))

    def evaluate_dwell(self) -> None:
        """Fires a left click when the cursor holds still for
        `dwell_time_s`, so a target can be activated by stopping over it
        instead of performing a gesture. Watches the real OS position, so
        it applies whether the stillness comes from head tracking or a
        physical mouse."""
        cal = self._config.calibration
        if not cal.dwell_click_enabled:
            self._dwell_anchor_x = None
            self._dwell_anchor_y = None
            self._dwell_fired = False
            return

        cur_x, cur_y = self._mouse.position

        if (
            self._dwell_anchor_x is None
            or abs(cur_x - self._dwell_anchor_x) > DWELL_STILL_PX
            or abs(cur_y - self._dwell_anchor_y) > DWELL_STILL_PX
        ):
            # First frame with dwell enabled, or the cursor moved -- (re)start
            # the dwell timer at the new position.
            self._dwell_anchor_x, self._dwell_anchor_y = float(cur_x), float(cur_y)
            self._dwell_started_at = self._clock()
            self._dwell_fired = False
            return

        if self._dwell_fired:
            return  # already clicked for this stillness; wait for a move

        if self._clock() - self._dwell_started_at >= cal.dwell_time_s:
            if self._on_action is not None:
                try:
                    self._on_action("dwell", "left_click", self._mouse.position)
                except Exception as exc:  # noqa: BLE001 - feedback must never block the click
                    print(f"facemesh-mouse: on_action failed ({exc!r})")
            _ACTIONS["left_click"](self._mouse)
            self._dwell_fired = True

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
        if action != "none" and self._on_action is not None:
            try:
                self._on_action(gesture_name, action, self._mouse.position)
            except Exception as exc:  # noqa: BLE001 - feedback must never block the click
                print(f"facemesh-mouse: on_action failed ({exc!r})")
        _ACTIONS[action](self._mouse)
