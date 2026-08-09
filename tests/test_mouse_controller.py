import pytest

from facemesh_mouse.config import AppConfig, CalibrationConfig
from facemesh_mouse.mouse_controller import MouseController, accelerate


class FakeMouse:
    def __init__(self, start=(500, 500)):
        self.position = start
        self.clicks: list[tuple[object, int]] = []

    def click(self, button, count) -> None:
        self.clicks.append((button, count))


def _config(
    sensitivity_x=0.025,
    sensitivity_y=0.05,
    acceleration=0.0,
    motion_threshold_px=0.0,
    yield_resume_after_s=3.0,
    dwell_click_enabled=False,
    dwell_time_s=1.0,
):
    return AppConfig(
        calibration=CalibrationConfig(
            sensitivity_x=sensitivity_x,
            sensitivity_y=sensitivity_y,
            acceleration=acceleration,
            motion_threshold_px=motion_threshold_px,
            yield_resume_after_s=yield_resume_after_s,
            dwell_click_enabled=dwell_click_enabled,
            dwell_time_s=dwell_time_s,
        ),
        gestures={},
    )


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def test_accelerate_returns_zero_for_zero_movement():
    assert accelerate(0.0, 0.5) == 0.0


def test_accelerate_preserves_sign():
    assert accelerate(-0.05, 0.5) < 0
    assert accelerate(0.05, 0.5) > 0


def test_accelerate_with_zero_acceleration_is_linear():
    """(|d| / reference) ** 0 == 1, so the curve collapses to a pass-through."""
    assert accelerate(0.037, 0.0) == pytest.approx(0.037)


def test_acceleration_damps_small_movements_more_than_large_ones():
    """The whole point of the curve: fine movements get quieter while big
    ones stay fast."""
    small, large = 0.01, 0.2

    small_ratio = accelerate(small, 0.5) / small
    large_ratio = accelerate(large, 0.5) / large

    assert small_ratio < large_ratio


def test_move_cursor_x_is_not_inverted():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    # movement of 4 camera px * 0.025 sensitivity = 0.1 -> 100px of a 1000px screen
    controller.move_cursor(4.0, 0.0)

    assert mouse.position[0] == pytest.approx(600, abs=1)
    assert mouse.position[1] == pytest.approx(500, abs=1)


def test_cursor_follows_the_user_through_the_real_mirroring_chain():
    """The one place the sign convention is actually decided: a raw camera
    frame, flipped the way FaceTracker.process flips it, tracked, and fed to
    the cursor. Every other test hands numbers straight to move_cursor and so
    cannot catch an inversion -- which is how one shipped."""
    import cv2
    import numpy as np

    from facemesh_mouse.point_tracker import PointTracker

    rng = np.random.default_rng(0)
    raw = cv2.GaussianBlur(rng.integers(0, 255, (240, 320), dtype=np.uint8), (5, 5), 0)
    # A front-facing camera sees the user's right side drift toward low x.
    raw_moved = cv2.warpAffine(raw, np.float32([[1, 0, -8], [0, 1, 0]]), (320, 240))

    tracker = PointTracker()
    nose, candidates = (160.0, 120.0), [(140.0, 100.0), (180.0, 140.0), (150.0, 130.0)]
    tracker.update(cv2.flip(raw, 1), nose, 200.0, candidates)
    tracker.update(cv2.flip(raw_moved, 1), nose, 200.0, candidates)

    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()
    controller.move_cursor(*tracker.get_movement())

    assert mouse.position[0] > 500, "user moved right, cursor must move right"


def test_move_cursor_ignores_non_finite_movement():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    controller.move_cursor(float("nan"), 0.0)

    assert mouse.position == (500, 500)


def test_move_cursor_y_is_not_inverted():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    controller.move_cursor(0.0, 2.0)  # 2 * 0.05 = 0.1 -> +100px

    assert mouse.position[1] == pytest.approx(600, abs=1)


def test_motion_threshold_zeroes_a_small_movement():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(acceleration=0.0, motion_threshold_px=50.0), (1000, 1000), mouse=mouse
    )
    controller.reanchor()

    controller.move_cursor(0.4, 0.0)  # 0.4 * 0.025 * 1000 = 10px, under the 50px threshold

    assert mouse.position == (500, 500)


def test_cursor_is_clamped_to_the_screen():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    controller.move_cursor(1000.0, 1000.0)

    assert 0 <= mouse.position[0] <= 999
    assert 0 <= mouse.position[1] <= 999


def test_reanchor_resyncs_to_the_real_os_cursor():
    mouse = FakeMouse(start=(300, 400))
    controller = MouseController(_config(), (1000, 1000), mouse=mouse)

    controller.reanchor()

    assert controller._cursor_x == 300
    assert controller._cursor_y == 400


def test_move_cursor_yields_when_the_cursor_diverges_from_the_last_write():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    mouse.position = (700, 500)  # simulate a physical-mouse touch
    controller.move_cursor(4.0, 0.0)

    assert controller.yielded is True
    assert mouse.position == (700, 500)  # untouched by tracked movement


def test_yielded_cursor_ignores_tracked_movement_until_the_quiet_period_elapses():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(acceleration=0.0, yield_resume_after_s=3.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    mouse.position = (700, 500)
    controller.move_cursor(4.0, 0.0)  # enters yielded at t=0
    assert controller.yielded is True

    clock.t = 2.9
    controller.move_cursor(4.0, 0.0)  # still within the quiet period
    assert controller.yielded is True
    assert mouse.position == (700, 500)

    clock.t = 3.1
    controller.move_cursor(4.0, 0.0)  # quiet period elapsed -> resumes
    assert controller.yielded is False


def test_continued_physical_movement_keeps_resetting_the_quiet_timer():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(acceleration=0.0, yield_resume_after_s=3.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    mouse.position = (700, 500)
    controller.move_cursor(0.0, 0.0)  # enters yielded at t=0

    clock.t = 2.9
    mouse.position = (750, 500)  # the user is still moving the physical mouse
    controller.move_cursor(0.0, 0.0)

    clock.t = 5.0  # 2.1s since the last movement -- well under the 3s quiet period
    controller.move_cursor(0.0, 0.0)
    assert controller.yielded is True


def test_resuming_from_yield_reanchors_with_no_jump():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(acceleration=0.0, yield_resume_after_s=3.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    mouse.position = (700, 500)
    controller.move_cursor(0.0, 0.0)

    clock.t = 3.1
    controller.move_cursor(0.0, 0.0)

    assert mouse.position == (700, 500)  # resume must not move the cursor
    assert controller._cursor_x == 700


def test_small_cursor_drift_is_not_mistaken_for_a_physical_move():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    mouse.position = (501, 500)  # within YIELD_DETECT_PX
    controller.move_cursor(4.0, 0.0)

    assert controller.yielded is False


def test_dwell_click_disabled_by_default_never_fires():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(), (1000, 1000), mouse=mouse, clock=clock)
    controller.reanchor()

    clock.t = 10.0
    controller.evaluate_dwell()

    assert mouse.clicks == []


def test_dwell_click_does_not_fire_before_the_time_elapses():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(dwell_click_enabled=True, dwell_time_s=1.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    controller.evaluate_dwell()  # starts the timer at t=0
    clock.t = 0.9
    controller.evaluate_dwell()

    assert mouse.clicks == []


def test_dwell_click_fires_after_holding_still_for_the_configured_time():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(dwell_click_enabled=True, dwell_time_s=1.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    controller.evaluate_dwell()  # starts the timer at t=0
    clock.t = 1.1
    controller.evaluate_dwell()

    assert len(mouse.clicks) == 1


def test_dwell_click_invokes_on_action_callback():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    calls = []
    controller = MouseController(
        _config(dwell_click_enabled=True, dwell_time_s=1.0),
        (1000, 1000),
        mouse=mouse,
        clock=clock,
        on_action=lambda *args: calls.append(args),
    )
    controller.reanchor()

    controller.evaluate_dwell()
    clock.t = 1.1
    controller.evaluate_dwell()

    assert calls == [("dwell", "left_click", mouse.position)]


def test_dwell_click_does_not_repeat_while_still_stationary():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(dwell_click_enabled=True, dwell_time_s=1.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    controller.evaluate_dwell()
    clock.t = 1.1
    controller.evaluate_dwell()
    clock.t = 3.0
    controller.evaluate_dwell()

    assert len(mouse.clicks) == 1


def test_dwell_click_fires_again_after_the_cursor_moves_away_and_settles():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(dwell_click_enabled=True, dwell_time_s=1.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    controller.evaluate_dwell()
    clock.t = 1.1
    controller.evaluate_dwell()
    assert len(mouse.clicks) == 1

    mouse.position = (700, 500)  # moved to a new target
    clock.t = 1.2
    controller.evaluate_dwell()  # restarts the timer at the new position
    clock.t = 2.3
    controller.evaluate_dwell()

    assert len(mouse.clicks) == 2


def test_dwell_click_ignores_movement_within_the_still_tolerance():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(dwell_click_enabled=True, dwell_time_s=1.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    controller.evaluate_dwell()
    clock.t = 0.5
    mouse.position = (501, 500)  # within DWELL_STILL_PX -- still "the same spot"
    controller.evaluate_dwell()
    clock.t = 1.1
    controller.evaluate_dwell()

    assert len(mouse.clicks) == 1


def test_reanchor_resets_a_stale_dwell_timer():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(dwell_click_enabled=True, dwell_time_s=1.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    controller.evaluate_dwell()  # timer running at t=0, unfired
    clock.t = 5.0
    controller.reanchor()  # e.g. resuming from pause -- must not carry the timer over

    controller.evaluate_dwell()  # this call only restarts the timer, at t=5.0
    assert mouse.clicks == []

    clock.t = 5.9  # under 1s since the restart
    controller.evaluate_dwell()
    assert mouse.clicks == []


from facemesh_mouse.config import GestureConfig


def test_fire_action_invokes_on_action_callback():
    mouse = FakeMouse()
    calls = []
    config = AppConfig(
        calibration=CalibrationConfig(),
        gestures={"blink_a": GestureConfig(action="left_click")},
    )
    controller = MouseController(
        config, (1000, 1000), mouse=mouse, on_action=lambda *args: calls.append(args)
    )

    controller.fire_action("blink_a")

    assert calls == [("blink_a", "left_click", mouse.position)]


def test_fire_action_does_not_invoke_on_action_for_none():
    mouse = FakeMouse()
    calls = []
    config = AppConfig(
        calibration=CalibrationConfig(),
        gestures={"blink_a": GestureConfig(action="none")},
    )
    controller = MouseController(
        config, (1000, 1000), mouse=mouse, on_action=lambda *args: calls.append(args)
    )

    controller.fire_action("blink_a")

    assert calls == []


def test_fire_action_still_clicks_when_on_action_raises():
    mouse = FakeMouse()
    config = AppConfig(
        calibration=CalibrationConfig(),
        gestures={"blink_a": GestureConfig(action="left_click")},
    )

    def _boom(*_args):
        raise RuntimeError("simulated feedback failure")

    controller = MouseController(config, (1000, 1000), mouse=mouse, on_action=_boom)

    controller.fire_action("blink_a")

    assert len(mouse.clicks) == 1
