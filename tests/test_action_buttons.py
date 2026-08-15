import ctypes
from unittest.mock import MagicMock

from facemesh_mouse.modules import config as config_mod
from facemesh_mouse.modules.config import default_config
from facemesh_mouse.ui import action_buttons
from facemesh_mouse.ui.click_feedback import GWL_EXSTYLE, WS_EX_TRANSPARENT


class _FakeEvent:
    def __init__(self, x_root, y_root, x=0):
        self.x_root = x_root
        self.y_root = y_root
        self.x = x


def test_is_click_within_threshold_on_both_axes():
    assert action_buttons.is_click((100, 100), (103, 102))


def test_is_click_exactly_at_the_threshold_is_a_click():
    t = action_buttons.CLICK_DRAG_THRESHOLD_PX
    assert action_buttons.is_click((100, 100), (100 + t, 100 - t))


def test_is_click_past_the_threshold_on_either_axis_is_a_drag():
    t = action_buttons.CLICK_DRAG_THRESHOLD_PX
    assert not action_buttons.is_click((100, 100), (100 + t + 1, 100))
    assert not action_buttons.is_click((100, 100), (100, 100 + t + 1))


def test_default_position_is_inset_from_the_bottom_right_corner():
    x, y = action_buttons.default_position(1000, 800)
    assert x == 1000 - action_buttons.WIDTH - action_buttons.MARGIN
    assert y == 800 - action_buttons.SIZE - action_buttons.MARGIN


def test_default_position_sits_above_a_reserved_taskbar():
    """winfo_screenheight() returns the full physical screen height, which
    includes the taskbar's strip -- without accounting for it, the default
    corner would place the buttons half-hidden behind the taskbar."""
    x, y = action_buttons.default_position(1000, 800, taskbar_reserved_px=48)
    assert x == 1000 - action_buttons.WIDTH - action_buttons.MARGIN
    assert y == 800 - action_buttons.SIZE - action_buttons.MARGIN - 48


def test_group_places_its_default_position_above_the_real_taskbar(monkeypatch, container):
    """ActionButtons must ask _taskbar_reserved_px for the real reservation
    and feed it into the default corner, not just default_position's own
    (untested-in-isolation) plumbing."""
    monkeypatch.setattr(action_buttons, "_taskbar_reserved_px", lambda screen_h: 48)

    buttons = action_buttons.ActionButtons(
        container, default_config(), "unused-config-path.json", (1000, 800)
    )

    expected_x, expected_y = action_buttons.default_position(1000, 800, 48)
    assert buttons._window.winfo_x() == int(expected_x)
    assert buttons._window.winfo_y() == int(expected_y)

    buttons.destroy()


def test_resolve_position_uses_the_saved_spot_when_it_still_fits():
    assert action_buttons.resolve_position(50.0, 60.0, 1000, 800) == (50.0, 60.0)


def test_resolve_position_falls_back_to_default_without_a_saved_spot():
    assert action_buttons.resolve_position(
        None, None, 1000, 800
    ) == action_buttons.default_position(1000, 800)


def test_resolve_position_falls_back_when_the_saved_spot_is_off_the_smaller_screen():
    assert action_buttons.resolve_position(
        1900.0, 1000.0, 1000, 800
    ) == action_buttons.default_position(1000, 800)


def test_resolve_position_accepts_the_saved_spot_exactly_at_the_far_edge():
    screen_w, screen_h = 1000, 800
    edge_x = screen_w - action_buttons.WIDTH
    edge_y = screen_h - action_buttons.SIZE
    assert action_buttons.resolve_position(edge_x, edge_y, screen_w, screen_h) == (edge_x, edge_y)


def test_group_builds_a_topmost_non_click_through_window(container):
    buttons = action_buttons.ActionButtons(
        container, default_config(), "unused-config-path.json", (1000, 800)
    )

    window = buttons._window
    assert window.winfo_exists()
    assert window.attributes("-topmost")

    parent_hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(parent_hwnd, GWL_EXSTYLE)
    assert not (styles & WS_EX_TRANSPARENT)  # must receive clicks, unlike the click-feedback pulse

    buttons.destroy()


def test_group_never_steals_activation_from_the_dictation_target(container):
    """Clicking this window must never focus itself instead of leaving the
    previously-focused text field active -- voice typing's recognized text
    would otherwise have nowhere to land."""
    buttons = action_buttons.ActionButtons(
        container, default_config(), "unused-config-path.json", (1000, 800)
    )

    parent_hwnd = ctypes.windll.user32.GetParent(buttons._window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(parent_hwnd, GWL_EXSTYLE)
    assert styles & action_buttons.WS_EX_NOACTIVATE

    buttons.destroy()


def test_a_small_release_on_the_left_half_opens_the_keyboard(monkeypatch, container, tmp_path):
    opened = []

    def _fake_open():
        opened.append(True)
        return True

    monkeypatch.setattr(action_buttons.virtual_keyboard, "open_virtual_keyboard", _fake_open)
    config_path = tmp_path / "config.json"
    config = default_config()
    buttons = action_buttons.ActionButtons(container, config, config_path, (1000, 800))

    buttons._on_press(_FakeEvent(500, 500, x=10))  # within the keyboard (left) circle
    buttons._on_release(_FakeEvent(502, 501, x=12))

    assert opened == [True]
    assert not config_path.exists()  # a click never writes to disk

    buttons.destroy()


def test_keyboard_click_shows_the_normal_pulse_when_it_opens(monkeypatch, container, tmp_path):
    monkeypatch.setattr(action_buttons.virtual_keyboard, "open_virtual_keyboard", lambda: True)
    pulse_mock = MagicMock()
    monkeypatch.setattr(action_buttons.click_feedback, "show_pulse", pulse_mock)
    config_path = tmp_path / "config.json"
    buttons = action_buttons.ActionButtons(container, default_config(), config_path, (1000, 800))

    buttons._on_press(_FakeEvent(500, 500, x=10))
    buttons._on_release(_FakeEvent(502, 501, x=12))

    pulse_mock.assert_called_once_with(buttons._window, 502, 501)

    buttons.destroy()


def test_keyboard_click_shows_a_warning_pulse_when_windows_declines_to_open_it(
    monkeypatch, container, tmp_path
):
    """Windows silently no-ops the touch keyboard when no editable text
    field has focus -- the button click still needs to give the user some
    feedback that it registered, or a real click and a swallowed click are
    indistinguishable."""
    monkeypatch.setattr(action_buttons.virtual_keyboard, "open_virtual_keyboard", lambda: False)
    pulse_mock = MagicMock()
    tooltip_mock = MagicMock()
    monkeypatch.setattr(action_buttons.click_feedback, "show_pulse", pulse_mock)
    monkeypatch.setattr(action_buttons.click_feedback, "show_tooltip", tooltip_mock)
    config_path = tmp_path / "config.json"
    buttons = action_buttons.ActionButtons(container, default_config(), config_path, (1000, 800))

    buttons._on_press(_FakeEvent(500, 500, x=10))
    buttons._on_release(_FakeEvent(502, 501, x=12))

    pulse_mock.assert_called_once_with(
        buttons._window, 502, 501, action_buttons.WARNING_PULSE_COLOR
    )
    tooltip_mock.assert_called_once_with(
        buttons._window, 502, 501, action_buttons.NO_FOCUS_TOOLTIP_TEXT
    )

    buttons.destroy()


def test_a_small_release_on_the_right_half_toggles_voice_typing(monkeypatch, container, tmp_path):
    toggled = []
    monkeypatch.setattr(
        action_buttons.voice_typing, "toggle_voice_typing", lambda: toggled.append(True)
    )
    config_path = tmp_path / "config.json"
    config = default_config()
    buttons = action_buttons.ActionButtons(container, config, config_path, (1000, 800))

    press_x = action_buttons.SIZE + 10  # within the mic (right) circle
    buttons._on_press(_FakeEvent(500, 500, x=press_x))
    buttons._on_release(_FakeEvent(502, 501, x=press_x + 2))

    assert toggled == [True]
    assert not config_path.exists()

    buttons.destroy()


def test_a_large_release_saves_the_new_position_without_clicking(monkeypatch, container, tmp_path):
    opened = []
    toggled = []
    monkeypatch.setattr(
        action_buttons.virtual_keyboard, "open_virtual_keyboard", lambda: opened.append(True)
    )
    monkeypatch.setattr(
        action_buttons.voice_typing, "toggle_voice_typing", lambda: toggled.append(True)
    )
    config_path = tmp_path / "config.json"
    config = default_config()
    buttons = action_buttons.ActionButtons(container, config, config_path, (1000, 800))

    buttons._on_press(_FakeEvent(500, 500, x=10))
    buttons._on_motion(_FakeEvent(560, 500))  # 60px -- moves the window
    buttons._on_release(_FakeEvent(560, 500, x=10))

    assert opened == []
    assert toggled == []
    assert config_path.exists()
    assert config.action_buttons.x is not None
    assert config.action_buttons.y is not None

    buttons.destroy()


def test_dragging_does_not_clobber_settings_saved_after_startup(container, tmp_path):
    """A user who saves calibration via the config window, then drags the
    buttons, must not have that calibration silently reverted on disk --
    ActionButtons must never write a stale whole-AppConfig snapshot."""
    path = tmp_path / "config.json"
    saved = default_config()
    saved.calibration.sensitivity_x = 0.09  # what the config window wrote
    config_mod.save_config(path, saved)

    stale = default_config()  # what main.py's app_config still holds
    buttons = action_buttons.ActionButtons(container, stale, path, (1000, 800))

    buttons._on_press(_FakeEvent(500, 500, x=10))
    buttons._on_motion(_FakeEvent(560, 500))
    buttons._on_release(_FakeEvent(560, 500, x=10))

    reloaded = config_mod.load_config(path)
    assert reloaded.calibration.sensitivity_x == 0.09
    assert reloaded.action_buttons.x is not None
    assert reloaded.action_buttons.y is not None

    buttons.destroy()


def test_reset_position_moves_the_window_and_saves(container, tmp_path):
    config_path = tmp_path / "config.json"
    config = default_config()
    buttons = action_buttons.ActionButtons(container, config, config_path, (1000, 800))

    # drag it somewhere else first
    buttons._on_press(_FakeEvent(500, 500, x=10))
    buttons._on_motion(_FakeEvent(560, 500))
    buttons._on_release(_FakeEvent(560, 500, x=10))
    moved_x = config.action_buttons.x

    buttons.reset_position()

    default_x, default_y = action_buttons.default_position(1000, 800)
    assert config.action_buttons.x == default_x
    assert config.action_buttons.y == default_y
    assert config.action_buttons.x != moved_x

    reloaded = config_mod.load_config(config_path)
    assert (reloaded.action_buttons.x, reloaded.action_buttons.y) == (default_x, default_y)

    buttons.destroy()
