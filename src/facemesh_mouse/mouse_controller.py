"""Cursor mapping/smoothing math + action execution via pynput.

The pure math (`map_normalized_to_screen`, `ema_smooth`) is separated from
the pynput-driving `MouseController` so it can be unit tested without a
real display or OS mouse.
"""
from __future__ import annotations

from pynput.mouse import Button, Controller

from .config import AppConfig
from .tracker import FaceMetrics

_ACTIONS = {
    "left_click": lambda m: m.click(Button.left, 1),
    "right_click": lambda m: m.click(Button.right, 1),
    "double_click": lambda m: m.click(Button.left, 2),
    "scroll_up": lambda m: m.scroll(0, 1),
    "scroll_down": lambda m: m.scroll(0, -1),
    "none": lambda m: None,
}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_scale(axis_min: float, axis_max: float, screen_dim: int, sensitivity: float) -> float:
    """How many screen pixels one unit of normalized nose movement covers,
    derived from the calibrated axis range and the user's sensitivity
    multiplier."""
    axis_range = (axis_max - axis_min) or 1e-6
    return (screen_dim / axis_range) * sensitivity


def apply_deadzone(delta: float, scale: float, deadzone_px: float) -> float:
    """Zeroes a raw normalized delta if its scaled (pixel) magnitude falls
    below the deadzone threshold; otherwise returns it unchanged."""
    if abs(delta * scale) < deadzone_px:
        return 0.0
    return delta


def ema_smooth(prev: float | None, new: float, weight_of_prev: float) -> float:
    """Exponential moving average. `weight_of_prev` close to 1.0 = smoother
    and slower to react; close to 0.0 = snappier and more jittery."""
    if prev is None:
        return new
    return weight_of_prev * prev + (1.0 - weight_of_prev) * new


class MouseController:
    def __init__(self, config: AppConfig, screen_size: tuple[int, int]) -> None:
        self._config = config
        self._screen_w, self._screen_h = screen_size
        self._mouse = Controller()
        self._smoothed_x: float | None = None
        self._smoothed_y: float | None = None

    def update_config(self, config: AppConfig) -> None:
        self._config = config

    def move_cursor(self, metrics: FaceMetrics) -> None:
        cal = self._config.calibration
        target_x, target_y = map_normalized_to_screen(
            metrics.nose_x,
            metrics.nose_y,
            cal.x_min,
            cal.x_max,
            cal.y_min,
            cal.y_max,
            self._screen_w,
            self._screen_h,
        )
        self._smoothed_x = ema_smooth(self._smoothed_x, target_x, cal.smoothing)
        self._smoothed_y = ema_smooth(self._smoothed_y, target_y, cal.smoothing)
        self._mouse.position = (int(self._smoothed_x), int(self._smoothed_y))

    def fire_action(self, gesture_name: str) -> None:
        action = self._config.gestures[gesture_name].action
        _ACTIONS[action](self._mouse)
