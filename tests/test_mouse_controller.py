import pytest

from facemesh_mouse.mouse_controller import ema_smooth, map_normalized_to_screen


def test_map_normalized_to_screen_center():
    x, y = map_normalized_to_screen(0.5, 0.5, 0.0, 1.0, 0.0, 1.0, 1920, 1080)
    assert x == pytest.approx(959, abs=1)
    assert y == pytest.approx(539, abs=1)


def test_map_normalized_to_screen_clamps_outside_calibration_range():
    x, y = map_normalized_to_screen(-1.0, 2.0, 0.3, 0.7, 0.3, 0.7, 1000, 1000)
    assert x == 0
    assert y == 999


def test_map_normalized_to_screen_respects_calibration_bounds():
    x, _y = map_normalized_to_screen(0.4, 0.5, 0.4, 0.6, 0.0, 1.0, 100, 100)
    assert x == 0  # at x_min -> left edge

    x, _y = map_normalized_to_screen(0.6, 0.5, 0.4, 0.6, 0.0, 1.0, 100, 100)
    assert x == 99  # at x_max -> right edge


def test_ema_smooth_first_sample_passthrough():
    assert ema_smooth(None, 42.0, 0.9) == 42.0


def test_ema_smooth_blends_toward_new_value():
    result = ema_smooth(prev=0.0, new=100.0, weight_of_prev=0.5)
    assert result == pytest.approx(50.0)


def test_ema_smooth_high_weight_reacts_slowly():
    result = ema_smooth(prev=0.0, new=100.0, weight_of_prev=0.9)
    assert result == pytest.approx(10.0)
