from facemesh_mouse.config import AppConfig, CalibrationConfig, GestureConfig
from facemesh_mouse.gestures import GestureEngine
from facemesh_mouse.tracker import FaceMetrics


def _metrics(ear_a=0.3, ear_b=0.3, mouth=0.1, eyebrow=0.05):
    return FaceMetrics(
        nose_x=0.5,
        nose_y=0.5,
        ear_a=ear_a,
        ear_b=ear_b,
        mouth_open_ratio=mouth,
        eyebrow_raise_ratio=eyebrow,
        landmarks=[],
    )


def _config(**overrides):
    gestures = {
        "blink_left": GestureConfig(action="left_click", threshold=0.2, cooldown_ms=0),
        "blink_right": GestureConfig(action="right_click", threshold=0.2, cooldown_ms=0),
        "blink_both": GestureConfig(action="none", threshold=0.2, cooldown_ms=0),
        "mouth_open": GestureConfig(action="double_click", threshold=0.3, cooldown_ms=0),
        "eyebrow_raised": GestureConfig(action="scroll_up", threshold=0.1, cooldown_ms=0),
    }
    gestures.update(overrides)
    return AppConfig(calibration=CalibrationConfig(), gestures=gestures)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_blink_left_fires_once_on_transition():
    clock = FakeClock()
    engine = GestureEngine(_config(), clock=clock)

    # eye A closes below threshold, eye B stays open
    fired = engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    assert fired == ["blink_left"]

    # holding the blink should not refire
    fired = engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    assert fired == []

    # releasing then re-closing fires again
    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    fired = engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    assert fired == ["blink_left"]


def test_blink_both_takes_precedence_over_single_eye_condition():
    clock = FakeClock()
    engine = GestureEngine(_config(), clock=clock)

    fired = engine.evaluate(_metrics(ear_a=0.1, ear_b=0.1))
    assert fired == ["blink_both"]


def test_mouth_open_and_eyebrow_can_fire_together():
    clock = FakeClock()
    engine = GestureEngine(_config(), clock=clock)

    fired = engine.evaluate(_metrics(mouth=0.5, eyebrow=0.2))
    assert set(fired) == {"mouth_open", "eyebrow_raised"}


def test_cooldown_blocks_rapid_retrigger():
    clock = FakeClock()
    gestures = {
        "blink_left": GestureConfig(action="left_click", threshold=0.2, cooldown_ms=1000),
        "blink_right": GestureConfig(action="right_click", threshold=0.2, cooldown_ms=0),
        "blink_both": GestureConfig(action="none", threshold=0.2, cooldown_ms=0),
        "mouth_open": GestureConfig(action="double_click", threshold=0.3, cooldown_ms=0),
        "eyebrow_raised": GestureConfig(action="scroll_up", threshold=0.1, cooldown_ms=0),
    }
    engine = GestureEngine(AppConfig(calibration=CalibrationConfig(), gestures=gestures), clock=clock)

    fired = engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    assert fired == ["blink_left"]

    # release and re-trigger within the cooldown window
    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    clock.t = 0.5  # 500ms later, cooldown is 1000ms
    fired = engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    assert fired == []

    # past the cooldown window it fires again
    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    clock.t = 1.1
    fired = engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    assert fired == ["blink_left"]
