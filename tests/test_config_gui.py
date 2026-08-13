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


def test_clicking_toggle_while_stopped_starts_saves_and_hides(window, tmp_path):
    engine = _FakeEngine()
    started = []
    win, config_path = _build(
        window, engine, tmp_path,
        on_start=lambda cfg: (started.append(cfg), engine.control_enabled.set()),
    )
    win.show()

    win._on_toggle()

    assert started
    assert config_path.exists()
    assert engine.control_enabled.is_set()
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


def test_clicking_toggle_while_active_stops_saves_and_stays_open(window, tmp_path):
    engine = _FakeEngine()
    engine.control_enabled.set()
    win, config_path = _build(window, engine, tmp_path)
    win.show()

    win._on_toggle()

    assert config_path.exists()
    assert not engine.control_enabled.is_set()
    assert window.state() == "normal"
    assert win._toggle_button.cget("text") == "Iniciar controle do mouse"


def test_closing_via_x_while_active_saves_hides_and_leaves_control_enabled(window, tmp_path):
    engine = _FakeEngine()
    engine.control_enabled.set()
    win, config_path = _build(window, engine, tmp_path)
    win.show()

    win._save_and_hide()

    assert config_path.exists()
    assert engine.control_enabled.is_set()
    assert window.state() == "withdrawn"


def test_closing_via_x_while_stopped_saves_hides_and_leaves_control_disabled(window, tmp_path):
    engine = _FakeEngine()
    win, config_path = _build(window, engine, tmp_path)
    win.show()

    win._save_and_hide()

    assert config_path.exists()
    assert not engine.control_enabled.is_set()
    assert window.state() == "withdrawn"
