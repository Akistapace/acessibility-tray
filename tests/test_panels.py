import tkinter as tk

import pytest

ctk = pytest.importorskip("customtkinter")

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


@pytest.fixture(scope="module")
def root():
    from facemesh_mouse.config_gui import create_root

    try:
        window = create_root()
    except tk.TclError as exc:  # no display available
        pytest.skip(f"Tk unavailable: {exc}")
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def container(root):
    """A fresh parent widget per test. The root itself is shared and never
    torn down mid-module: repeatedly creating and destroying Tk roots in one
    process fails intermittently under pytest's output capture."""
    frame = ctk.CTkFrame(root)
    yield frame
    frame.destroy()


def test_calibration_panel_builds_and_updates(container):
    config = default_config()
    panel = CalibrationPanel(container, config)
    panel.frame.pack()
    container.update()

    panel.update(_metrics())

    assert panel.frame.winfo_exists()


def test_capture_records_the_most_extreme_value_not_the_last(container):
    config = default_config()
    panel = CalibrationPanel(container, config)

    panel.start_capture("left")
    panel.update(_metrics(nose_x=0.40))
    panel.update(_metrics(nose_x=0.22))  # the true extreme
    panel.update(_metrics(nose_x=0.35))  # drifted back
    panel.stop_capture()

    assert config.calibration.x_min == pytest.approx(0.22)


def test_capture_down_records_the_maximum(container):
    config = default_config()
    panel = CalibrationPanel(container, config)

    panel.start_capture("down")
    panel.update(_metrics(nose_y=0.60))
    panel.update(_metrics(nose_y=0.81))
    panel.update(_metrics(nose_y=0.70))
    panel.stop_capture()

    assert config.calibration.y_max == pytest.approx(0.81)


def test_cancel_capture_discards_without_writing_to_config(container):
    config = default_config()
    before = config.calibration.x_min
    panel = CalibrationPanel(container, config)

    panel.start_capture("left")
    panel.update(_metrics(nose_x=0.05))
    panel.cancel_capture()

    assert config.calibration.x_min == before
    assert panel.recording_direction is None


def test_starting_a_capture_disables_the_other_buttons(container):
    panel = CalibrationPanel(container, default_config())

    panel.start_capture("left")
    assert str(panel.buttons["right"].cget("state")) == "disabled"

    panel.stop_capture()
    assert str(panel.buttons["right"].cget("state")) == "normal"


def test_sliders_write_into_the_config(container):
    config = default_config()
    panel = CalibrationPanel(container, config)

    panel.deadzone_var.set(9.0)
    panel.on_deadzone_change()
    panel.sensitivity_var.set(2.5)
    panel.on_sensitivity_change()

    assert config.calibration.deadzone_px == pytest.approx(9.0)
    assert config.calibration.sensitivity == pytest.approx(2.5)


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
