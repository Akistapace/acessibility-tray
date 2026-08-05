"""Edge-triggered gesture detection from per-frame face metrics.

Each gesture has a threshold and a cooldown. A gesture fires once when its
condition transitions from false to true, and won't fire again until both
the condition has gone false and released, AND the cooldown has elapsed
(prevents a held expression, or two rapid re-triggers, from spamming
actions).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .config import AppConfig
from .tracker import FaceMetrics


def _condition(name: str, metrics: FaceMetrics, threshold: float) -> bool:
    if name == "blink_left":
        return metrics.ear_a < threshold and metrics.ear_b >= threshold
    if name == "blink_right":
        return metrics.ear_b < threshold and metrics.ear_a >= threshold
    if name == "blink_both":
        return metrics.ear_a < threshold and metrics.ear_b < threshold
    if name == "mouth_open":
        return metrics.mouth_open_ratio > threshold
    if name == "eyebrow_raised":
        return metrics.eyebrow_raise_ratio > threshold
    raise ValueError(f"Unknown gesture: {name}")


@dataclass
class _GestureState:
    active: bool = False
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
            met = _condition(name, metrics, gesture_cfg.threshold)

            if not met:
                state.active = False
                continue

            if state.active:
                continue  # already firing this hold; wait for release

            cooldown_elapsed = (now - state.last_fired_at) * 1000.0 >= gesture_cfg.cooldown_ms
            if cooldown_elapsed:
                fired.append(name)
                state.last_fired_at = now
            state.active = True

        return fired
