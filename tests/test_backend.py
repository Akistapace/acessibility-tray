import sys

import numpy as np

from facemesh_mouse import backend
from facemesh_mouse.modules import config as config_mod
from facemesh_mouse.modules.config import AppConfig
from facemesh_mouse.modules.engine import Engine


def _config_with_sensitivity(value: float) -> AppConfig:
    cfg = config_mod.default_config()
    cfg.calibration.sensitivity_x = value
    return cfg


def test_start_command_sets_control_enabled():
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config())

    server.handle_command({"type": "start"})

    assert engine.control_enabled.is_set()


def test_stop_command_clears_control_enabled():
    engine = Engine(config_mod.default_config())
    engine.control_enabled.set()
    server = backend.BackendServer(engine, config_mod.default_config())

    server.handle_command({"type": "stop"})

    assert not engine.control_enabled.is_set()


def test_pause_and_resume_commands():
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config())

    server.handle_command({"type": "pause"})
    assert engine.paused.is_set()

    server.handle_command({"type": "resume"})
    assert not engine.paused.is_set()


def test_set_preview_command_toggles_flag():
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({"type": "set_preview", "enabled": True})
    assert server.preview_enabled is True

    server.handle_command({"type": "set_preview", "enabled": False})
    assert server.preview_enabled is False


def test_update_config_command_applies_to_engine_and_updates_server_config():
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config())

    server.handle_command({
        "type": "update_config",
        "config": config_mod.config_to_dict(_config_with_sensitivity(0.09)),
    })

    assert engine._config.calibration.sensitivity_x == 0.09
    assert server.config.calibration.sensitivity_x == 0.09


def test_save_config_command_writes_to_disk(tmp_path):
    path = tmp_path / "config.json"
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config(), config_path=str(path))

    server.handle_command({
        "type": "save_config",
        "config": config_mod.config_to_dict(_config_with_sensitivity(0.07)),
    })

    assert config_mod.load_config(path).calibration.sensitivity_x == 0.07


def test_save_config_command_merges_partial_payload_onto_disk(tmp_path):
    path = tmp_path / "config.json"
    config_mod.save_config(path, _config_with_sensitivity(0.09))
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config(), config_path=str(path))

    server.handle_command({
        "type": "save_config",
        "config": {"action_buttons": {"x": 120.0, "y": 640.0}},
    })

    reloaded = config_mod.load_config(path)
    assert reloaded.calibration.sensitivity_x == 0.09
    assert reloaded.action_buttons.x == 120.0
    assert reloaded.action_buttons.y == 640.0


def test_open_keyboard_command_sends_keyboard_result(monkeypatch):
    sent = []
    server = backend.BackendServer(
        Engine(config_mod.default_config()), config_mod.default_config(), send=sent.append
    )
    monkeypatch.setattr(backend.virtual_keyboard, "open_virtual_keyboard", lambda: True)

    server.handle_command({"type": "open_keyboard", "x": 100, "y": 200})

    assert sent == [{"type": "keyboard_result", "opened": True, "x": 100, "y": 200}]


def test_open_keyboard_command_reports_a_decline(monkeypatch):
    sent = []
    server = backend.BackendServer(
        Engine(config_mod.default_config()), config_mod.default_config(), send=sent.append
    )
    monkeypatch.setattr(backend.virtual_keyboard, "open_virtual_keyboard", lambda: False)

    server.handle_command({"type": "open_keyboard", "x": 5, "y": 6})

    assert sent == [{"type": "keyboard_result", "opened": False, "x": 5, "y": 6}]


def test_open_voice_typing_command_calls_toggle(monkeypatch):
    calls = []
    monkeypatch.setattr(backend.voice_typing, "toggle_voice_typing", lambda: calls.append(1))
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({"type": "open_voice_typing"})

    assert calls == [1]


def test_get_config_command_sends_the_current_config(monkeypatch):
    sent = []
    config = _config_with_sensitivity(0.06)
    server = backend.BackendServer(
        Engine(config_mod.default_config()), config, send=sent.append
    )

    server.handle_command({"type": "get_config"})

    assert sent == [{"type": "config", "config": config_mod.config_to_dict(config)}]


def test_unknown_command_type_is_ignored():
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())
    server.handle_command({"type": "not_a_real_command"})  # must not raise


def test_handle_command_catches_and_logs_a_failing_handler(capsys):
    # A malformed command must never take the whole backend down: this
    # payload makes config_from_dict raise AttributeError inside the real
    # update_config handler, and handle_command has to absorb it.
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({"type": "update_config", "config": None})  # must not raise

    assert "update_config" in capsys.readouterr().err


def test_status_snapshot_reflects_engine_flags():
    engine = Engine(config_mod.default_config())
    engine.paused.set()

    assert backend._status_snapshot(engine) == {
        "control_enabled": False,
        "paused": True,
        "no_face": False,
        "yielded": False,
    }


def test_encode_frame_produces_a_frame_message_with_progress_for_every_gesture():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    config = config_mod.default_config()

    message = backend._encode_frame(frame, None, config, seq=3)

    assert message["type"] == "frame"
    assert message["seq"] == 3
    assert set(message["gesture_progress"]) == set(config_mod.GESTURE_NAMES)
    # No face detected this frame -- every bar reads empty, matching the
    # no_face status pushed alongside it, rather than freezing at a stale
    # value from the last frame that had a face.
    assert all(v == 0.0 for v in message["gesture_progress"].values())


def test_set_cursor_theme_command_updates_config_and_calls_apply_cursor(monkeypatch):
    calls = []
    monkeypatch.setattr(
        backend.cursor_theme, "apply_cursor", lambda *a, **kw: calls.append((a, kw))
    )
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({
        "type": "set_cursor_theme",
        "size_px": 64,
        "mode": "mista",
        "custom_color": "#112233",
    })

    assert server.config.cursor.size_px == 64
    assert server.config.cursor.mode == "mista"
    assert server.config.cursor.custom_color == "#112233"
    assert calls == [((64, "mista", "#112233"), {})]


def test_set_cursor_theme_command_clamps_and_falls_back_like_config_loading(monkeypatch):
    monkeypatch.setattr(backend.cursor_theme, "apply_cursor", lambda *a, **kw: None)
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({
        "type": "set_cursor_theme",
        "size_px": 999,
        "mode": "not_a_real_mode",
        "custom_color": "#000000",
    })

    assert server.config.cursor.size_px == config_mod.CURSOR_SIZE_RANGE[1]
    assert server.config.cursor.mode == "default"


def test_save_config_command_merges_partial_cursor_payload_onto_disk(tmp_path):
    path = tmp_path / "config.json"
    saved = config_mod.default_config()
    saved.cursor.mode = "black"
    config_mod.save_config(path, saved)
    server = backend.BackendServer(
        Engine(config_mod.default_config()), config_mod.default_config(), config_path=str(path)
    )

    server.handle_command({
        "type": "save_config",
        "config": {"cursor": {"size_px": 80}},
    })

    reloaded = config_mod.load_config(path)
    assert reloaded.cursor.mode == "black"  # untouched field survives the merge
    assert reloaded.cursor.size_px == 80


def test_main_restores_cursor_when_camera_fails_to_open_after_a_startup_theme_apply(monkeypatch):
    # main() itself has no other unit tests in this suite -- it wires a real
    # camera, real stdin, and background threads, none of which the rest of
    # this file touches. This test only exercises the one path relevant to
    # the regression: a saved non-default cursor theme gets applied at
    # startup, camera open then fails, and the process must still restore
    # the cursor before exiting rather than leaving it permanently altered
    # (see cursor_theme.restore_cursor's shutdown-path call in this same
    # function for the normal-exit case this mirrors).
    class _FakeEngine:
        def __init__(self, config, on_action=None):
            self.config = config
            self.on_action = on_action

        def open_camera(self):
            return False

    themed = config_mod.default_config()
    themed.cursor.mode = "black"
    themed.cursor.size_px = 64
    themed.calibration.click_logging_enabled = False  # avoid a real clicks.log write

    apply_calls = []
    restore_calls = []
    monkeypatch.setattr(backend.config_mod, "load_config", lambda path: themed)
    monkeypatch.setattr(
        backend.cursor_theme, "apply_cursor", lambda *a, **kw: apply_calls.append((a, kw))
    )
    monkeypatch.setattr(
        backend.cursor_theme, "restore_cursor", lambda *a, **kw: restore_calls.append((a, kw))
    )
    monkeypatch.setattr(backend, "Engine", _FakeEngine)

    # main() reassigns sys.stdout internally and never puts it back --
    # restore it ourselves so this test doesn't corrupt capture for tests
    # that run after it in the same process.
    original_stdout = sys.stdout
    try:
        backend.main()
    finally:
        sys.stdout = original_stdout

    assert apply_calls == [((64, "black", themed.cursor.custom_color), {})]
    assert restore_calls == [((), {})]
