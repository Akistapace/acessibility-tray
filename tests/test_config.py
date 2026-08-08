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
    original.calibration.sensitivity_x = 0.04
    original.gestures["mouth_open"].action = "scroll_down"

    config_mod.save_config(path, original)
    loaded = config_mod.load_config(path)

    assert loaded.calibration.sensitivity_x == 0.04
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


def test_default_config_has_the_tracking_defaults():
    cal = config_mod.default_config().calibration
    assert cal.sensitivity_x == 0.025
    assert cal.sensitivity_y == 0.05
    assert cal.acceleration == 0.5
    assert cal.motion_threshold_px == 0.0


def test_tracking_fields_round_trip(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.calibration.sensitivity_x = 0.04
    original.calibration.acceleration = 0.8

    config_mod.save_config(path, original)
    loaded = config_mod.load_config(path)

    assert loaded.calibration.sensitivity_x == 0.04
    assert loaded.calibration.acceleration == 0.8


def test_legacy_calibration_keys_are_ignored_and_gestures_survive(tmp_path):
    """A config from before the optical-flow switch has four-point bounds
    that have no sensitivity equivalent. They are dropped; the defaults
    apply; the user's gesture mappings must still migrate."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "calibration": {"x_min": 0.4, "x_max": 0.6, "smoothing": 0.7, "deadzone_px": 15.0},
                "gestures": {"blink_left": {"action": "scroll_up"}},
            }
        )
    )

    loaded = config_mod.load_config(path)

    assert loaded.calibration.sensitivity_x == 0.025
    assert loaded.calibration.motion_threshold_px == 0.0
    assert not hasattr(loaded.calibration, "x_min")
    assert loaded.gestures["blink_a"].action == "scroll_up"


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
