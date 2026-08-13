import pytest

from facemesh_mouse.modules import config as config_mod
from facemesh_mouse.modules.config import AppConfig, CalibrationConfig, GestureConfig
from facemesh_mouse.modules.gestures import GestureEngine, trigger_progress
from facemesh_mouse.modules.tracker import FaceMetrics


def _metrics(ear_a=0.3, ear_b=0.3, mouth=0.1, eyebrow=0.05, eyebrow_b=None, mouth_shift=0.0):
    return FaceMetrics(
        nose_x=0.5,
        nose_y=0.5,
        ear_a=ear_a,
        ear_b=ear_b,
        mouth_open_ratio=mouth,
        eyebrow_raise_a=eyebrow,
        eyebrow_raise_b=eyebrow if eyebrow_b is None else eyebrow_b,
        mouth_shift_ratio=mouth_shift,
        landmarks=[],
    )


def _config(hold_ms=0, **overrides):
    gestures = {
        "blink_a": GestureConfig(action="left_click", threshold=0.2, cooldown_ms=0, hold_ms=hold_ms),
        "blink_b": GestureConfig(action="right_click", threshold=0.2, cooldown_ms=0, hold_ms=hold_ms),
        "blink_both": GestureConfig(action="none", threshold=0.2, cooldown_ms=0, hold_ms=hold_ms),
        "eyebrow_a": GestureConfig(action="none", threshold=0.1, cooldown_ms=0, hold_ms=hold_ms),
        "eyebrow_b": GestureConfig(action="none", threshold=0.1, cooldown_ms=0, hold_ms=hold_ms),
        "eyebrow_both": GestureConfig(action="none", threshold=0.1, cooldown_ms=0, hold_ms=hold_ms),
        "mouth_open": GestureConfig(action="double_click", threshold=0.3, cooldown_ms=0, hold_ms=hold_ms),
        "mouth_left": GestureConfig(action="none", threshold=0.05, cooldown_ms=0, hold_ms=hold_ms),
        "mouth_right": GestureConfig(action="none", threshold=0.05, cooldown_ms=0, hold_ms=hold_ms),
    }
    gestures.update(overrides)
    return AppConfig(calibration=CalibrationConfig(), gestures=gestures)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_blink_a_fires_once_on_transition():
    engine = GestureEngine(_config(), clock=FakeClock())

    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_blink_both_takes_precedence_over_single_eye_condition():
    engine = GestureEngine(_config(), clock=FakeClock())
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.1)) == ["blink_both"]


def test_eyebrow_a_fires_alone_without_eyebrow_b():
    engine = GestureEngine(_config(), clock=FakeClock())
    assert engine.evaluate(_metrics(eyebrow=0.2, eyebrow_b=0.05)) == ["eyebrow_a"]


def test_eyebrow_both_requires_both_sides_raised():
    engine = GestureEngine(_config(), clock=FakeClock())
    assert engine.evaluate(_metrics(eyebrow=0.2, eyebrow_b=0.2)) == ["eyebrow_both"]


def test_mouth_left_and_right_are_direction_specific():
    engine = GestureEngine(_config(), clock=FakeClock())
    assert engine.evaluate(_metrics(mouth_shift=-0.2)) == ["mouth_left"]

    engine.evaluate(_metrics(mouth_shift=0.0))
    assert engine.evaluate(_metrics(mouth_shift=0.2)) == ["mouth_right"]


def test_lateral_mouth_gestures_require_a_closed_mouth():
    engine = GestureEngine(_config(), clock=FakeClock())

    # shifted far left, but the mouth is open -> not a closed-mouth gesture
    assert engine.evaluate(_metrics(mouth_shift=-0.2, mouth=0.5)) == ["mouth_open"]

    # same shift with the mouth closed does fire
    assert engine.evaluate(_metrics(mouth_shift=-0.2, mouth=0.05)) == ["mouth_left"]


def test_cooldown_blocks_rapid_retrigger():
    clock = FakeClock()
    engine = GestureEngine(
        _config(blink_a=GestureConfig(action="left_click", threshold=0.2, cooldown_ms=1000, hold_ms=0)),
        clock=clock,
    )

    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]

    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    clock.t = 0.5
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    clock.t = 1.1
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_natural_blink_does_not_fire_a_single_eye_gesture():
    """The reported bug: a natural blink closes both eyes slightly out of
    sync, and the asymmetric window used to satisfy blink_a immediately.
    With a hold time it must never fire."""
    clock = FakeClock()
    engine = GestureEngine(_config(hold_ms=400), clock=clock)

    clock.t = 0.0
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []  # eye A closes first

    clock.t = 0.08
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.1)) == []  # eye B follows 80ms later

    clock.t = 0.14
    assert engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3)) == []  # both reopen, ~140ms blink

    clock.t = 1.0
    assert engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3)) == []  # and nothing fires later


def test_deliberate_hold_fires_once_after_the_hold_time():
    clock = FakeClock()
    engine = GestureEngine(_config(hold_ms=400), clock=clock)

    clock.t = 0.0
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    clock.t = 0.399
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    clock.t = 0.400
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]

    clock.t = 0.900
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []  # no refire while held


def test_releasing_and_reholding_fires_again():
    clock = FakeClock()
    engine = GestureEngine(_config(hold_ms=400), clock=clock)

    clock.t = 0.0
    engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    clock.t = 0.5
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]

    clock.t = 0.6
    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))  # release

    clock.t = 0.7
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []
    clock.t = 1.2
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_hold_ms_zero_fires_immediately():
    engine = GestureEngine(_config(hold_ms=0), clock=FakeClock())
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_hold_blocked_by_cooldown_fires_when_the_cooldown_expires():
    """A hold that completes inside the cooldown window must stay armed and
    fire once the cooldown passes -- not be silently thrown away."""
    clock = FakeClock()
    engine = GestureEngine(
        _config(blink_a=GestureConfig(action="left_click", threshold=0.2, cooldown_ms=1000, hold_ms=400)),
        clock=clock,
    )

    # first gesture: held past 400ms, fires at t=0.4
    clock.t = 0.0
    engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    clock.t = 0.4
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]

    # release, then start a second hold well inside the 1000ms cooldown
    clock.t = 0.5
    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    clock.t = 0.6
    engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))

    # hold completes at t=1.0, but the cooldown runs until t=1.4
    clock.t = 1.0
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    # still held once the cooldown has cleared -> it fires instead of being
    # lost (1.45 rather than the exact 1.4 boundary to stay clear of a
    # float-subtraction rounding artifact: 1.4 - 0.4 == 0.9999999999999999)
    clock.t = 1.45
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_indefinite_hold_still_fires_only_once():
    """The at-most-once-per-hold guarantee must survive Fix 1."""
    clock = FakeClock()
    engine = GestureEngine(
        _config(blink_a=GestureConfig(action="left_click", threshold=0.2, cooldown_ms=100, hold_ms=200)),
        clock=clock,
    )

    clock.t = 0.0
    engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    clock.t = 0.2
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]

    # keep holding well past the cooldown -- must not repeat
    for t in (0.5, 1.0, 2.0, 5.0):
        clock.t = t
        assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []


def test_trigger_progress_reaches_one_at_an_above_threshold_trigger():
    assert trigger_progress("mouth_open", _metrics(mouth=0.35), 0.35) == pytest.approx(1.0)


def test_trigger_progress_reaches_one_at_a_below_threshold_trigger():
    assert trigger_progress("blink_a", _metrics(ear_a=0.21), 0.21) == pytest.approx(1.0)


def test_trigger_progress_is_partial_at_rest_for_blinks():
    progress = trigger_progress("blink_a", _metrics(ear_a=0.30), 0.21)
    assert 0.0 < progress < 1.0


def test_trigger_progress_stays_in_the_unit_range():
    assert trigger_progress("blink_a", _metrics(ear_a=0.01), 0.21) == 1.0
    assert trigger_progress("mouth_open", _metrics(mouth=99.0), 0.35) == 1.0
    assert trigger_progress("mouth_left", _metrics(mouth_shift=0.5), 0.05) == 0.0


def test_trigger_progress_covers_every_gesture_name():
    metrics = _metrics()
    for name in config_mod.GESTURE_NAMES:
        value = trigger_progress(name, metrics, 0.2)
        assert 0.0 <= value <= 1.0


def test_two_eye_blink_only_fills_the_both_eyes_bar():
    closed = _metrics(ear_a=0.1, ear_b=0.1)

    assert trigger_progress("blink_a", closed, 0.21) == 0.0
    assert trigger_progress("blink_b", closed, 0.21) == 0.0
    assert trigger_progress("blink_both", closed, 0.21) == pytest.approx(1.0)


def test_raising_both_eyebrows_only_fills_the_both_bar():
    raised = _metrics(eyebrow=0.3, eyebrow_b=0.3)

    assert trigger_progress("eyebrow_a", raised, 0.15) == 0.0
    assert trigger_progress("eyebrow_b", raised, 0.15) == 0.0
    assert trigger_progress("eyebrow_both", raised, 0.15) == pytest.approx(1.0)


def test_lateral_mouth_bar_is_empty_while_the_mouth_is_open():
    shifted_open = _metrics(mouth_shift=-0.2, mouth=0.5)
    assert trigger_progress("mouth_left", shifted_open, 0.05) == 0.0

    shifted_closed = _metrics(mouth_shift=-0.2, mouth=0.05)
    assert trigger_progress("mouth_left", shifted_closed, 0.05) == pytest.approx(1.0)
