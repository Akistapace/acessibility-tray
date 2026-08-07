"""Edge-triggered gesture detection from per-frame face metrics.

Each gesture has a threshold, a hold time, and a cooldown. A gesture fires
once its condition has been continuously true for `hold_ms` -- which is what
keeps involuntary expressions (above all a natural blink, whose two eyes
close a few frames apart) from firing actions the user never intended. It
fires at most once per hold; releasing the condition rearms it. The cooldown
additionally rate-limits repeated deliberate gestures.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .config import AppConfig
from .tracker import FaceMetrics

# A lateral-mouth gesture only counts while the mouth is closed. This is a
# property of the detector rather than something the user tunes per gesture,
# so it is a constant instead of a config field.
MOUTH_CLOSED_MAX = 0.15

# Gestures whose condition is "metric fell BELOW the threshold". Everything
# else fires when its metric rises above it.
_FIRES_BELOW = {"blink_a", "blink_b", "blink_both"}


def _condition(name: str, metrics: FaceMetrics, threshold: float) -> bool:
    if name == "blink_a":
        return metrics.ear_a < threshold and metrics.ear_b >= threshold
    if name == "blink_b":
        return metrics.ear_b < threshold and metrics.ear_a >= threshold
    if name == "blink_both":
        return metrics.ear_a < threshold and metrics.ear_b < threshold
    if name == "eyebrow_a":
        return metrics.eyebrow_raise_a > threshold and metrics.eyebrow_raise_b <= threshold
    if name == "eyebrow_b":
        return metrics.eyebrow_raise_b > threshold and metrics.eyebrow_raise_a <= threshold
    if name == "eyebrow_both":
        return metrics.eyebrow_raise_a > threshold and metrics.eyebrow_raise_b > threshold
    if name == "mouth_open":
        return metrics.mouth_open_ratio > threshold
    if name == "mouth_left":
        return (
            metrics.mouth_shift_ratio < -threshold
            and metrics.mouth_open_ratio <= MOUTH_CLOSED_MAX
        )
    if name == "mouth_right":
        return (
            metrics.mouth_shift_ratio > threshold
            and metrics.mouth_open_ratio <= MOUTH_CLOSED_MAX
        )
    raise ValueError(f"Unknown gesture: {name}")


def _progress_value(name: str, metrics: FaceMetrics) -> float:
    """The single metric that governs how close `name` is to triggering.
    Where a gesture needs two sides to agree, the lagging side governs."""
    if name == "blink_a":
        return metrics.ear_a
    if name == "blink_b":
        return metrics.ear_b
    if name == "blink_both":
        return max(metrics.ear_a, metrics.ear_b)
    if name == "eyebrow_a":
        return metrics.eyebrow_raise_a
    if name == "eyebrow_b":
        return metrics.eyebrow_raise_b
    if name == "eyebrow_both":
        return min(metrics.eyebrow_raise_a, metrics.eyebrow_raise_b)
    if name == "mouth_open":
        return metrics.mouth_open_ratio
    if name == "mouth_left":
        return -metrics.mouth_shift_ratio
    if name == "mouth_right":
        return metrics.mouth_shift_ratio
    raise ValueError(f"Unknown gesture: {name}")


def trigger_progress(name: str, metrics: FaceMetrics, threshold: float) -> float:
    """How close `name` is to firing, as 0.0 (far) to 1.0 (at or past the
    trigger point). Shared with the config GUI's live bars so the display and
    the detector can never disagree about which direction means 'closer'."""
    value = _progress_value(name, metrics)
    threshold = threshold or 1e-6
    if name in _FIRES_BELOW:
        ratio = threshold / max(value, 1e-6)
    else:
        ratio = value / threshold
    return max(0.0, min(1.0, ratio))


@dataclass
class _GestureState:
    met_since: float | None = None  # when the condition last became true
    fired_this_hold: bool = False
    last_fired_at: float = -1e9


class GestureEngine:
    def __init__(self, config: AppConfig, clock=time.monotonic) -> None:
        self._config = config
        self._clock = clock
        self._state = {name: _GestureState() for name in config.gestures}

    def update_config(self, config: AppConfig) -> None:
        self._config = config
        for name in config.gestures:
            self._state.setdefault(name, _GestureState())

    def evaluate(self, metrics: FaceMetrics) -> list[str]:
        """Returns the list of gesture names that fired on this frame."""
        fired = []
        now = self._clock()
        for name, gesture_cfg in self._config.gestures.items():
            state = self._state[name]

            if not _condition(name, metrics, gesture_cfg.threshold):
                state.met_since = None
                state.fired_this_hold = False
                continue

            if state.met_since is None:
                state.met_since = now

            if state.fired_this_hold:
                continue

            if (now - state.met_since) * 1000.0 < gesture_cfg.hold_ms:
                continue

            if (now - state.last_fired_at) * 1000.0 >= gesture_cfg.cooldown_ms:
                fired.append(name)
                state.last_fired_at = now
            # Marked either way: a cooldown-blocked hold must not retry every
            # frame until the user releases the expression.
            state.fired_this_hold = True

        return fired
