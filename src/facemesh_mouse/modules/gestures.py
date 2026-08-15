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

# Actions that keep firing every cooldown_ms for as long as the gesture
# stays held, instead of firing once per hold -- so scrolling continues
# while the user holds the expression rather than needing a full
# release-and-reraise per tick.
_REPEATING_ACTIONS = {"scroll_up", "scroll_down"}

# Actions that press on the rising edge and release on the falling edge,
# instead of firing an atomic action -- reported via GestureEngine.evaluate's
# return (the press) and GestureEngine.last_released (the release).
# freeze_cursor is deliberately NOT here: it's a plain edge-triggered
# toggle (MouseController flips `frozen` on each fire, like flicking a
# switch), not a hold -- holding one expression continuously while also
# performing a second gesture (e.g. mouth-open to drag) is impractical, so
# one pulse locks the cursor and a second, separate pulse unlocks it.
_HOLD_ACTIONS = {"left_drag"}

# Actions where the condition is meant to represent an ongoing state (button
# held, scroll repeating) rather than a discrete press. A continuous metric
# like mouth-open ratio dips below threshold for single frames from
# tracking noise alone; on these actions that dip must not immediately drop
# the hold -- see the release-debounce below.
_CONTINUOUS_ACTIONS = _HOLD_ACTIONS | _REPEATING_ACTIONS


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


def _is_reachable(name: str, metrics: FaceMetrics, threshold: float) -> bool:
    """Whether `name`'s non-primary requirements are currently satisfied.

    `_progress_value` only tracks a gesture's primary metric, so without this
    a blocked gesture would show a full bar it can never act on -- e.g. a
    normal two-eye blink driving blink_a, blink_b and blink_both to 100% when
    only blink_both can fire.
    """
    if name == "blink_a":
        return metrics.ear_b >= threshold
    if name == "blink_b":
        return metrics.ear_a >= threshold
    if name == "eyebrow_a":
        return metrics.eyebrow_raise_b <= threshold
    if name == "eyebrow_b":
        return metrics.eyebrow_raise_a <= threshold
    if name in ("mouth_left", "mouth_right"):
        return metrics.mouth_open_ratio <= MOUTH_CLOSED_MAX
    return True


def trigger_progress(name: str, metrics: FaceMetrics, threshold: float) -> float:
    """How close `name` is to firing, as 0.0 (far) to 1.0 (at or past the
    trigger point). Shared with the config GUI's live bars so the display and
    the detector can never disagree about which direction means 'closer' --
    and so a gesture that is structurally blocked by another gesture's
    exclusion clause (e.g. blink_a while both eyes are closed) reads 0.0
    instead of a misleading full bar. The bar reflects both direction and
    reachability."""
    if not _is_reachable(name, metrics, threshold):
        return 0.0
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
    release_pending_since: float | None = None  # when the condition first dipped false mid-hold


class GestureEngine:
    def __init__(self, config: AppConfig, clock=time.monotonic) -> None:
        self._config = config
        self._clock = clock
        self._state = {name: _GestureState() for name in config.gestures}
        self.last_released: list[str] = []

    def update_config(self, config: AppConfig) -> None:
        self._config = config
        for name in config.gestures:
            self._state.setdefault(name, _GestureState())

    def evaluate(self, metrics: FaceMetrics) -> list[str]:
        """Returns the list of gesture names that fired on this frame.
        Also refreshes `last_released` with any hold-action gestures (e.g.
        drag) whose condition just released -- read it right after calling
        this, before the next frame's call overwrites it."""
        fired = []
        released = []
        now = self._clock()
        for name, gesture_cfg in self._config.gestures.items():
            state = self._state[name]
            continuous = gesture_cfg.action in _CONTINUOUS_ACTIONS

            if not _condition(name, metrics, gesture_cfg.threshold):
                if state.fired_this_hold and continuous:
                    # Debounce the release the same way the press is
                    # debounced: a single-frame dip below threshold (jaw
                    # wobble, landmark jitter) must not drop a held
                    # drag/freeze or interrupt a scroll repeat -- only a
                    # dip that lasts a full hold_ms counts as a real release.
                    if state.release_pending_since is None:
                        state.release_pending_since = now
                    elif (now - state.release_pending_since) * 1000.0 >= gesture_cfg.hold_ms:
                        if gesture_cfg.action in _HOLD_ACTIONS:
                            released.append(name)
                        state.met_since = None
                        state.fired_this_hold = False
                        state.release_pending_since = None
                    continue
                state.met_since = None
                state.fired_this_hold = False
                state.release_pending_since = None
                continue

            state.release_pending_since = None

            if state.met_since is None:
                state.met_since = now

            if state.fired_this_hold:
                # A repeating action (scroll) keeps re-firing at the
                # cooldown cadence for as long as the gesture stays held,
                # instead of the once-per-hold guard applied below.
                if (
                    gesture_cfg.action in _REPEATING_ACTIONS
                    and (now - state.last_fired_at) * 1000.0 >= gesture_cfg.cooldown_ms
                ):
                    fired.append(name)
                    state.last_fired_at = now
                continue

            if (now - state.met_since) * 1000.0 < gesture_cfg.hold_ms:
                continue

            if (now - state.last_fired_at) * 1000.0 >= gesture_cfg.cooldown_ms:
                fired.append(name)
                state.last_fired_at = now
                # Only a real fire arms the once-per-hold guard: a hold
                # blocked by the cooldown stays armed and fires the moment
                # the cooldown expires while still held, instead of being
                # thrown away. Re-checking the elapsed times each frame costs
                # two float subtractions per gesture -- negligible.
                state.fired_this_hold = True

        self.last_released = released
        return fired
