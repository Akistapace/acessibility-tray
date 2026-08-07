import pytest

from facemesh_mouse.mouse_controller import (
    apply_deadzone,
    compute_scale,
    ema_smooth,
)


def test_ema_smooth_first_sample_passthrough():
    assert ema_smooth(None, 42.0, 0.9) == 42.0


def test_ema_smooth_blends_toward_new_value():
    result = ema_smooth(prev=0.0, new=100.0, weight_of_prev=0.5)
    assert result == pytest.approx(50.0)


def test_ema_smooth_high_weight_reacts_slowly():
    result = ema_smooth(prev=0.0, new=100.0, weight_of_prev=0.9)
    assert result == pytest.approx(10.0)


def test_compute_scale_uses_screen_dim_over_axis_range():
    scale = compute_scale(0.3, 0.7, 1000, sensitivity=1.0)
    assert scale == pytest.approx(1000 / 0.4)


def test_compute_scale_sensitivity_multiplies_linearly():
    base = compute_scale(0.3, 0.7, 1000, sensitivity=1.0)
    doubled = compute_scale(0.3, 0.7, 1000, sensitivity=2.0)
    assert doubled == pytest.approx(base * 2)


def test_compute_scale_zero_range_does_not_divide_by_zero():
    scale = compute_scale(0.5, 0.5, 1000, sensitivity=1.0)
    assert scale > 0


def test_apply_deadzone_blocks_small_scaled_delta():
    # |0.001 * 1000| = 1.0px, below the 4px deadzone
    assert apply_deadzone(0.001, scale=1000, deadzone_px=4.0) == 0.0


def test_apply_deadzone_passes_large_scaled_delta_unchanged():
    # |0.01 * 1000| = 10px, above the 4px deadzone
    assert apply_deadzone(0.01, scale=1000, deadzone_px=4.0) == 0.01


from facemesh_mouse.config import AppConfig, CalibrationConfig
from facemesh_mouse.mouse_controller import MouseController
from facemesh_mouse.tracker import FaceMetrics


class FakeMouse:
    def __init__(self, start=(500, 500)):
        self.position = start


def _config(sensitivity=1.0, deadzone_px=0.0, smoothing=0.0):
    return AppConfig(
        calibration=CalibrationConfig(
            x_min=0.3,
            x_max=0.7,
            y_min=0.3,
            y_max=0.7,
            smoothing=smoothing,
            deadzone_px=deadzone_px,
            sensitivity=sensitivity,
        ),
        gestures={},
    )


def _metrics(nose_x=0.5, nose_y=0.5):
    return FaceMetrics(
        nose_x=nose_x,
        nose_y=nose_y,
        ear_a=0.3,
        ear_b=0.3,
        mouth_open_ratio=0.1,
        eyebrow_raise_a=0.05,
        eyebrow_raise_b=0.05,
        mouth_shift_ratio=0.0,
        landmarks=[],
    )


def test_reanchor_sets_state_from_current_os_cursor_position():
    mouse = FakeMouse(start=(300, 400))
    controller = MouseController(_config(), (1000, 1000), mouse=mouse)

    controller.reanchor(_metrics(nose_x=0.5, nose_y=0.5))

    assert controller._prev_nose_x == 0.5
    assert controller._prev_nose_y == 0.5
    assert controller._target_x == 300
    assert controller._target_y == 400
    assert controller._smoothed_x == 300
    assert controller._smoothed_y == 400


def test_move_cursor_after_reanchor_applies_scaled_delta_with_no_smoothing():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(sensitivity=1.0, deadzone_px=0.0, smoothing=0.0), (1000, 1000), mouse=mouse
    )
    controller.reanchor(_metrics(nose_x=0.5, nose_y=0.5))

    # scale_x = 1000 / 0.4 = 2500; moving nose by +0.02 -> +50px
    controller.move_cursor(_metrics(nose_x=0.52, nose_y=0.5))

    assert mouse.position[0] == pytest.approx(550, abs=1)
    assert mouse.position[1] == pytest.approx(500, abs=1)


def test_move_cursor_ignores_movement_below_deadzone():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(sensitivity=1.0, deadzone_px=100.0, smoothing=0.0), (1000, 1000), mouse=mouse
    )
    controller.reanchor(_metrics(nose_x=0.5, nose_y=0.5))

    # scale_x = 2500; delta 0.001 -> 2.5px, well under the 100px deadzone
    controller.move_cursor(_metrics(nose_x=0.501, nose_y=0.5))

    assert mouse.position == (500, 500)


def test_move_cursor_accumulates_sub_deadzone_movement_across_frames():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(sensitivity=1.0, deadzone_px=10.0, smoothing=0.0), (1000, 1000), mouse=mouse
    )
    controller.reanchor(_metrics(nose_x=0.5, nose_y=0.5))

    # scale_x = 2500; each step below is individually under the 10px deadzone
    controller.move_cursor(_metrics(nose_x=0.501, nose_y=0.5))  # 2.5px from anchor -> no movement yet
    assert mouse.position == (500, 500)

    controller.move_cursor(_metrics(nose_x=0.502, nose_y=0.5))  # still measured from the same anchor -> 5px -> still no movement
    assert mouse.position == (500, 500)

    controller.move_cursor(_metrics(nose_x=0.505, nose_y=0.5))  # 12.5px from the same anchor -> crosses the 10px deadzone
    assert mouse.position[0] > 500
