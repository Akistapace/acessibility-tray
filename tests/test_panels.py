import tkinter as tk

import pytest

from facemesh_mouse.calibration_panel import CalibrationPanel
from facemesh_mouse.config import default_config
from facemesh_mouse.tracker import FaceMetrics


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


# `root` and `container` fixtures live in tests/conftest.py -- shared across
# every GUI test module in this session so only one Tk root is ever created.


def test_calibration_panel_builds(container):
    panel = CalibrationPanel(container, default_config())
    panel.frame.pack()
    container.update()

    assert panel.frame.winfo_exists()


def test_calibration_panel_has_a_slider_per_tuning_field(container):
    panel = CalibrationPanel(container, default_config())

    assert set(panel.sliders) == {
        "sensitivity_x",
        "sensitivity_y",
        "acceleration",
        "motion_threshold_px",
        "dwell_time_s",
        "yield_resume_after_s",
    }


def test_click_logging_switch_writes_into_the_config(container):
    config = default_config()
    panel = CalibrationPanel(container, config)

    panel._click_logging_var.set(False)
    panel.apply_to_config()

    assert config.calibration.click_logging_enabled is False


def test_click_logging_switch_starts_from_the_configs_value(container):
    config = default_config()
    config.calibration.click_logging_enabled = False

    panel = CalibrationPanel(container, config)

    assert panel._click_logging_var.get() is False


def test_sliders_write_their_field_into_the_config(container):
    config = default_config()
    panel = CalibrationPanel(container, config)

    panel.sliders["sensitivity_x"].set(0.08)
    panel.sliders["acceleration"].set(0.9)
    panel.apply_to_config()

    assert config.calibration.sensitivity_x == pytest.approx(0.08, abs=1e-3)
    assert config.calibration.acceleration == pytest.approx(0.9, abs=1e-3)


def test_sliders_start_from_the_configs_values(container):
    config = default_config()
    config.calibration.sensitivity_y = 0.07

    panel = CalibrationPanel(container, config)

    assert panel.sliders["sensitivity_y"].get() == pytest.approx(0.07, abs=1e-3)


def test_dwell_switch_starts_from_the_configs_value(container):
    config = default_config()
    config.calibration.dwell_click_enabled = True

    panel = CalibrationPanel(container, config)

    assert panel.dwell_switch.get() == 1


def test_dwell_switch_and_slider_write_into_the_config(container):
    config = default_config()
    panel = CalibrationPanel(container, config)

    panel.dwell_switch.select()
    panel.sliders["dwell_time_s"].set(2.5)
    panel.apply_to_config()

    assert config.calibration.dwell_click_enabled is True
    assert config.calibration.dwell_time_s == pytest.approx(2.5, abs=1e-3)


def test_update_is_a_no_op(container):
    panel = CalibrationPanel(container, default_config())
    panel.update(_metrics())  # nothing on this tab is live any more

    assert panel.frame.winfo_exists()


from facemesh_mouse.config import GESTURE_NAMES
from facemesh_mouse.gesture_panel import ACTION_LABELS, GESTURE_LABELS, GesturePanel


def test_gesture_panel_has_a_row_per_gesture(container):
    panel = GesturePanel(container, default_config())
    assert set(panel.rows) == set(GESTURE_NAMES)


def test_every_gesture_has_a_portuguese_label():
    assert set(GESTURE_LABELS) == set(GESTURE_NAMES)


def test_gesture_panel_updates_every_bar(container):
    panel = GesturePanel(container, default_config())
    panel.frame.pack()
    container.update()

    panel.update(_metrics())

    for name in GESTURE_NAMES:
        value = panel.rows[name].bar.get()
        assert 0.0 <= value <= 1.0


def test_blink_bar_fills_as_the_eye_closes(container):
    panel = GesturePanel(container, default_config())

    panel.update(_metrics())  # eyes open
    open_value = panel.rows["blink_a"].bar.get()

    closing = _metrics()
    closing.ear_a = 0.21  # exactly at the default threshold
    panel.update(closing)

    assert panel.rows["blink_a"].bar.get() > open_value


def test_apply_to_config_writes_action_and_hold_time(container):
    config = default_config()
    panel = GesturePanel(container, config)

    panel.rows["mouth_left"].action_var.set(ACTION_LABELS["scroll_up"])
    panel.rows["mouth_left"].hold_var.set(700)
    panel.apply_to_config()

    assert config.gestures["mouth_left"].action == "scroll_up"
    assert config.gestures["mouth_left"].hold_ms == 700


def test_panel_starts_from_the_configs_current_values(container):
    config = default_config()
    config.gestures["blink_a"].action = "scroll_down"
    config.gestures["blink_a"].hold_ms = 250

    panel = GesturePanel(container, config)

    assert panel.rows["blink_a"].action_var.get() == ACTION_LABELS["scroll_down"]
    assert panel.rows["blink_a"].hold_var.get() == 250


def test_create_root_returns_a_usable_tk_root(root):
    assert isinstance(root, tk.Tk)

    root.deiconify()
    root.update()
    assert root.winfo_viewable()

    root.withdraw()
    root.update()
    assert not root.winfo_viewable()
