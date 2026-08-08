import pytest

from facemesh_mouse.config import AppConfig, CalibrationConfig
from facemesh_mouse.mouse_controller import MouseController, accelerate


class FakeMouse:
    def __init__(self, start=(500, 500)):
        self.position = start


def _config(sensitivity_x=0.025, sensitivity_y=0.05, acceleration=0.0, motion_threshold_px=0.0):
    return AppConfig(
        calibration=CalibrationConfig(
            sensitivity_x=sensitivity_x,
            sensitivity_y=sensitivity_y,
            acceleration=acceleration,
            motion_threshold_px=motion_threshold_px,
        ),
        gestures={},
    )


def test_accelerate_returns_zero_for_zero_movement():
    assert accelerate(0.0, 0.5) == 0.0


def test_accelerate_preserves_sign():
    assert accelerate(-0.05, 0.5) < 0
    assert accelerate(0.05, 0.5) > 0


def test_accelerate_with_zero_acceleration_is_linear():
    """|d * 5| ** 0 == 1, so the curve collapses to a pass-through."""
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
