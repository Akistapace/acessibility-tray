import ctypes

from facemesh_mouse.modules.config import default_config
from facemesh_mouse.ui import keyboard_button
from facemesh_mouse.ui.click_feedback import GWL_EXSTYLE, WS_EX_TRANSPARENT


class _FakeEvent:
    def __init__(self, x_root, y_root):
        self.x_root = x_root
        self.y_root = y_root


def test_is_click_within_threshold_on_both_axes():
    assert keyboard_button.is_click((100, 100), (103, 102))


def test_is_click_exactly_at_the_threshold_is_a_click():
    t = keyboard_button.CLICK_DRAG_THRESHOLD_PX
    assert keyboard_button.is_click((100, 100), (100 + t, 100 - t))


def test_is_click_past_the_threshold_on_either_axis_is_a_drag():
    t = keyboard_button.CLICK_DRAG_THRESHOLD_PX
    assert not keyboard_button.is_click((100, 100), (100 + t + 1, 100))
    assert not keyboard_button.is_click((100, 100), (100, 100 + t + 1))


def test_default_position_is_inset_from_the_bottom_right_corner():
    x, y = keyboard_button.default_position(1000, 800)
    assert x == 1000 - keyboard_button.SIZE - keyboard_button.MARGIN
    assert y == 800 - keyboard_button.SIZE - keyboard_button.MARGIN


def test_resolve_position_uses_the_saved_spot_when_it_still_fits():
    assert keyboard_button.resolve_position(50.0, 60.0, 1000, 800) == (50.0, 60.0)


def test_resolve_position_falls_back_to_default_without_a_saved_spot():
    assert keyboard_button.resolve_position(
        None, None, 1000, 800
    ) == keyboard_button.default_position(1000, 800)


def test_resolve_position_falls_back_when_the_saved_spot_is_off_the_smaller_screen():
    # saved from a larger, previous screen -- doesn't fit the current one
    assert keyboard_button.resolve_position(
        1900.0, 1000.0, 1000, 800
    ) == keyboard_button.default_position(1000, 800)


def test_button_builds_a_topmost_non_click_through_window(container):
    button = keyboard_button.KeyboardButton(
        container, default_config(), "unused-config-path.json", (1000, 800)
    )

    window = button._window
    assert window.winfo_exists()
    assert window.attributes("-topmost")

    parent_hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(parent_hwnd, GWL_EXSTYLE)
    assert not (styles & WS_EX_TRANSPARENT)  # must receive clicks, unlike the click-feedback pulse

    button.destroy()


def test_a_small_release_opens_the_keyboard_without_saving(monkeypatch, container, tmp_path):
    opened = []
    monkeypatch.setattr(
        keyboard_button.virtual_keyboard, "open_virtual_keyboard", lambda: opened.append(True)
    )
    config_path = tmp_path / "config.json"
    config = default_config()
    button = keyboard_button.KeyboardButton(container, config, config_path, (1000, 800))

    button._on_press(_FakeEvent(500, 500))
    button._on_release(_FakeEvent(502, 501))  # 2px on each axis -- within threshold

    assert opened == [True]
    assert not config_path.exists()  # a click never writes to disk

    button.destroy()


def test_a_large_release_saves_the_new_position_without_opening(monkeypatch, container, tmp_path):
    opened = []
    monkeypatch.setattr(
        keyboard_button.virtual_keyboard, "open_virtual_keyboard", lambda: opened.append(True)
    )
    config_path = tmp_path / "config.json"
    config = default_config()
    button = keyboard_button.KeyboardButton(container, config, config_path, (1000, 800))

    button._on_press(_FakeEvent(500, 500))
    button._on_motion(_FakeEvent(560, 500))  # 60px -- moves the window
    button._on_release(_FakeEvent(560, 500))

    assert opened == []
    assert config_path.exists()
    assert config.keyboard_button.x is not None
    assert config.keyboard_button.y is not None

    button.destroy()
