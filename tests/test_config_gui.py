import threading

import customtkinter as ctk
import pytest

from facemesh_mouse.modules.config import default_config
from facemesh_mouse.ui.config_gui import ConfigWindow


class _FakeState:
    def snapshot(self):
        return None, None


class _FakeEngine:
    def __init__(self) -> None:
        self.control_enabled = threading.Event()
        self.paused = threading.Event()
        self.state = _FakeState()


@pytest.fixture
def window(root):
    """A fresh Toplevel per test -- ConfigWindow drives title/protocol/
    geometry directly on whatever it's given, so it can't share a window
    with another test the way panel tests share `container`."""
    top = ctk.CTkToplevel(root)
    top.withdraw()
    yield top
    top.destroy()


def _build(window, engine, tmp_path, on_start=None):
    config_path = tmp_path / "config.json"
    return ConfigWindow(
        window,
        engine,
        default_config(),
        str(config_path),
        on_start=on_start or (lambda cfg: None),
    ), config_path


def test_toggle_shows_iniciar_when_control_is_not_enabled(window, tmp_path):
    engine = _FakeEngine()
    win, _ = _build(window, engine, tmp_path)

    assert win._toggle_button.cget("text") == "Iniciar controle do mouse"
    assert win._status_label.cget("text") == "Controle parado"
    assert win._toggle_button.cget("fg_color") != "#c0392b"


def test_clicking_toggle_while_stopped_starts_applies_edits_and_hides(window, tmp_path):
    """Iniciar must apply pending panel edits to the running engine even
    though -- per the explicit-save redesign -- it no longer writes
    anything to disk on its own."""
    engine = _FakeEngine()
    started = []
    win, config_path = _build(
        window, engine, tmp_path,
        on_start=lambda cfg: (started.append(cfg), engine.control_enabled.set()),
    )
    win.show()

    win._on_toggle()

    assert started
    assert not config_path.exists()  # Iniciar applies live, but never saves on its own
    assert engine.control_enabled.is_set()
    assert window.state() == "withdrawn"


def test_show_reflects_paused_state_set_externally(window, tmp_path):
    """Paused is normally toggled from the tray icon or Ctrl+Alt+P, outside
    this window entirely -- reopening it must show that, not silently
    claim "Controle ativo" while the cursor is actually yielded to the
    physical mouse."""
    engine = _FakeEngine()
    engine.control_enabled.set()
    win, _ = _build(window, engine, tmp_path)
    win.show()
    assert win._toggle_button.cget("text") == "Parar controle do mouse"

    engine.paused.set()
    win.show()

    assert win._toggle_button.cget("text") == "Retomar controle do mouse"
    assert win._status_label.cget("text") == "Controle pausado"


def test_clicking_toggle_while_paused_resumes_applies_edits_and_hides(window, tmp_path):
    engine = _FakeEngine()
    engine.control_enabled.set()
    engine.paused.set()
    started = []
    win, config_path = _build(
        window, engine, tmp_path, on_start=lambda cfg: started.append(cfg)
    )
    win.show()

    win._on_toggle()

    assert started  # pending panel edits still get applied to the engine
    assert not config_path.exists()  # resuming, like Iniciar, never saves on its own
    assert not engine.paused.is_set()
    assert engine.control_enabled.is_set()  # resume must not also stop control
    assert window.state() == "withdrawn"


def test_show_refreshes_toggle_for_control_enabled_after_construction(window, tmp_path):
    """Mirrors main.py's skip-wizard path: control_enabled is set directly
    on the engine, bypassing the window, sometime after ConfigWindow is
    built. Reopening the window must still reflect it."""
    engine = _FakeEngine()
    win, _ = _build(window, engine, tmp_path)
    assert win._toggle_button.cget("text") == "Iniciar controle do mouse"

    engine.control_enabled.set()
    win.show()

    assert win._toggle_button.cget("text") == "Parar controle do mouse"
    assert win._status_label.cget("text") == "Controle ativo"
    assert win._toggle_button.cget("fg_color") == "#c0392b"


def test_clicking_toggle_while_active_stops_without_saving_and_stays_open(window, tmp_path):
    engine = _FakeEngine()
    engine.control_enabled.set()
    win, config_path = _build(window, engine, tmp_path)
    win.show()

    win._on_toggle()

    assert not config_path.exists()  # Parar no longer saves on its own
    assert not engine.control_enabled.is_set()
    assert window.state() == "normal"
    assert win._toggle_button.cget("text") == "Iniciar controle do mouse"


def test_closing_via_x_while_active_hides_without_saving_and_leaves_control_enabled(window, tmp_path):
    engine = _FakeEngine()
    engine.control_enabled.set()
    win, config_path = _build(window, engine, tmp_path)
    win.show()

    win._save_and_hide()

    assert not config_path.exists()  # closing the window no longer saves on its own
    assert engine.control_enabled.is_set()
    assert window.state() == "withdrawn"


def test_closing_via_x_while_stopped_hides_without_saving_and_leaves_control_disabled(window, tmp_path):
    engine = _FakeEngine()
    win, config_path = _build(window, engine, tmp_path)
    win.show()

    win._save_and_hide()

    assert not config_path.exists()
    assert not engine.control_enabled.is_set()
    assert window.state() == "withdrawn"


def test_clicking_salvar_writes_the_config_and_flashes_confirmation(window, tmp_path):
    engine = _FakeEngine()
    win, config_path = _build(window, engine, tmp_path)
    win.show()

    win._on_save()

    assert config_path.exists()
    assert win._save_button.cget("text") == "Salvo"


def test_salvar_does_not_start_or_stop_control(window, tmp_path):
    engine = _FakeEngine()
    win, _ = _build(window, engine, tmp_path)
    win.show()

    win._on_save()

    assert not engine.control_enabled.is_set()


def test_apply_panel_edits_syncs_the_action_buttons_position(window, tmp_path):
    """A drag that happened after the window was built (tracked on
    `_live_config`, the object main.py's ActionButtons shares) must not be
    lost by a save built from the window's own deep-copied `_config`."""
    engine = _FakeEngine()
    win, config_path = _build(window, engine, tmp_path)
    win._live_config.action_buttons.x = 111.0
    win._live_config.action_buttons.y = 222.0

    win._save_config()

    from facemesh_mouse.modules import config as config_mod

    reloaded = config_mod.load_config(config_path)
    assert (reloaded.action_buttons.x, reloaded.action_buttons.y) == (111.0, 222.0)


def test_reset_position_delegates_to_the_action_buttons(window, tmp_path):
    from unittest.mock import MagicMock

    engine = _FakeEngine()
    action_buttons = MagicMock()
    win, _ = _build(window, engine, tmp_path)
    win._action_buttons = action_buttons

    win._on_reset_position()

    action_buttons.reset_position.assert_called_once()


def test_reset_position_is_a_noop_without_action_buttons(window, tmp_path):
    engine = _FakeEngine()
    win, _ = _build(window, engine, tmp_path)
    win._action_buttons = None

    win._on_reset_position()  # must not raise
