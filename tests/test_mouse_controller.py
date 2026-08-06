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
