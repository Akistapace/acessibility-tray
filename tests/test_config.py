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
    path.write_text(json.dumps({"gestures": {"blink_a": {"action": "right_click"}}}))

    loaded = config_mod.load_config(path)

    assert loaded.gestures["blink_a"].action == "right_click"
    # untouched gesture keeps its default action
    assert loaded.gestures["mouth_open"].action == config_mod.DEFAULT_ACTIONS["mouth_open"]


def test_load_config_invalid_action_falls_back_to_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gestures": {"blink_a": {"action": "not_a_real_action"}}}))

    loaded = config_mod.load_config(path)

    assert loaded.gestures["blink_a"].action == config_mod.DEFAULT_ACTIONS["blink_a"]


def test_load_config_invalid_json_returns_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not valid json")

    loaded = config_mod.load_config(path)

    assert loaded.calibration == config_mod.default_config().calibration


def test_default_config_has_deadzone_and_sensitivity_defaults():
    cfg = config_mod.default_config()
    assert cfg.calibration.deadzone_px == 4.0
    assert cfg.calibration.sensitivity == 1.0


def test_load_config_partial_file_merges_deadzone_and_sensitivity_with_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"calibration": {"deadzone_px": 8.0}}))

    loaded = config_mod.load_config(path)

    assert loaded.calibration.deadzone_px == 8.0
    assert loaded.calibration.sensitivity == config_mod.default_config().calibration.sensitivity


def test_save_then_load_round_trip_includes_deadzone_and_sensitivity(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.calibration.deadzone_px = 6.5
    original.calibration.sensitivity = 1.75

    config_mod.save_config(path, original)
    loaded = config_mod.load_config(path)

    assert loaded.calibration.deadzone_px == 6.5
    assert loaded.calibration.sensitivity == 1.75


def test_default_config_has_the_nine_gestures():
    cfg = config_mod.default_config()
    assert set(cfg.gestures) == {
        "blink_a",
        "blink_b",
        "blink_both",
        "eyebrow_a",
        "eyebrow_b",
        "eyebrow_both",
        "mouth_open",
        "mouth_left",
        "mouth_right",
    }


def test_hold_ms_defaults_and_round_trips(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    assert original.gestures["blink_a"].hold_ms == 400

    original.gestures["blink_a"].hold_ms = 250
    config_mod.save_config(path, original)

    assert config_mod.load_config(path).gestures["blink_a"].hold_ms == 250


def test_legacy_blink_names_migrate_to_the_a_b_names(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "gestures": {
                    "blink_left": {"action": "scroll_up"},
                    "blink_right": {"action": "scroll_down"},
                }
            }
        )
    )

    loaded = config_mod.load_config(path)

    assert loaded.gestures["blink_a"].action == "scroll_up"
    assert loaded.gestures["blink_b"].action == "scroll_down"


def test_legacy_eyebrow_raised_migrates_to_eyebrow_both(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gestures": {"eyebrow_raised": {"action": "scroll_up"}}}))

    loaded = config_mod.load_config(path)

    assert loaded.gestures["eyebrow_both"].action == "scroll_up"


def test_legacy_name_does_not_override_an_already_migrated_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "gestures": {
                    "eyebrow_raised": {"action": "scroll_up"},
                    "eyebrow_both": {"action": "double_click"},
                }
            }
        )
    )

    loaded = config_mod.load_config(path)

    assert loaded.gestures["eyebrow_both"].action == "double_click"
