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
