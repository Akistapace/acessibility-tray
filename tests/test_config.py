import json

from facemesh_mouse import config as config_mod


def test_default_config_has_all_gestures():
    cfg = config_mod.default_config()
    assert set(cfg.gestures.keys()) == set(config_mod.GESTURE_NAMES)


def test_load_config_missing_file_returns_default(tmp_path):
    cfg = config_mod.load_config(tmp_path / "does_not_exist.json")
    default = config_mod.default_config()
    assert cfg.calibration == default.calibration
    assert cfg.gestures.keys() == default.gestures.keys()


def test_save_then_load_round_trip(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.calibration.x_min = 0.1
    original.gestures["mouth_open"].action = "scroll_down"

    config_mod.save_config(path, original)
    loaded = config_mod.load_config(path)

    assert loaded.calibration.x_min == 0.1
    assert loaded.gestures["mouth_open"].action == "scroll_down"


def test_load_config_partial_file_merges_with_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gestures": {"blink_left": {"action": "right_click"}}}))

    loaded = config_mod.load_config(path)

    assert loaded.gestures["blink_left"].action == "right_click"
    # untouched gesture keeps its default action
    assert loaded.gestures["mouth_open"].action == config_mod.DEFAULT_ACTIONS["mouth_open"]


def test_load_config_invalid_action_falls_back_to_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gestures": {"blink_left": {"action": "not_a_real_action"}}}))

    loaded = config_mod.load_config(path)

    assert loaded.gestures["blink_left"].action == config_mod.DEFAULT_ACTIONS["blink_left"]


def test_load_config_invalid_json_returns_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not valid json")

    loaded = config_mod.load_config(path)

    assert loaded.calibration == config_mod.default_config().calibration
