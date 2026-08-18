"""Load/save the app's JSON config: calibration + gesture-to-action mapping."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

VALID_ACTIONS = {
    "none",
    "left_click",
    "right_click",
    "double_click",
    "scroll_up",
    "scroll_down",
    "left_drag",
    "freeze_cursor",
}

CURSOR_SIZE_RANGE = (32, 96)
VALID_CURSOR_MODES = {"default", "white", "black", "custom", "mista"}

GESTURE_NAMES = [
    "blink_a",
    "blink_b",
    "blink_both",
    "eyebrow_a",
    "eyebrow_b",
    "eyebrow_both",
    "mouth_open",
    "mouth_left",
    "mouth_right",
]

# Gesture names used by older config.json files, mapped to their current
# name. Migrated on load so an existing setup keeps its mappings.
LEGACY_GESTURE_NAMES = {
    "blink_left": "blink_a",
    "blink_right": "blink_b",
    "eyebrow_raised": "eyebrow_both",
}

DEFAULT_THRESHOLDS = {
    "blink_a": 0.21,
    "blink_b": 0.21,
    "blink_both": 0.21,
    "eyebrow_a": 0.15,
    "eyebrow_b": 0.15,
    "eyebrow_both": 0.15,
    "mouth_open": 0.35,
    "mouth_left": 0.05,
    "mouth_right": 0.05,
}

DEFAULT_ACTIONS = {
    "blink_a": "left_click",
    "blink_b": "right_click",
    "blink_both": "none",
    "eyebrow_a": "none",
    "eyebrow_b": "none",
    "eyebrow_both": "none",
    "mouth_open": "double_click",
    "mouth_left": "none",
    "mouth_right": "none",
}

DEFAULT_COOLDOWN_MS = {
    "blink_a": 400,
    "blink_b": 400,
    "blink_both": 400,
    "eyebrow_a": 400,
    "eyebrow_b": 400,
    "eyebrow_both": 400,
    "mouth_open": 600,
    "mouth_left": 400,
    "mouth_right": 400,
}

# How long a gesture's condition must hold before it fires. The default is
# comfortably above a natural blink (~100-150ms), which is what stops
# involuntary expressions from firing actions.
DEFAULT_HOLD_MS = {name: 400 for name in GESTURE_NAMES}


@dataclass
class CalibrationConfig:
    """Cursor tuning. Vertical sensitivity is twice horizontal because heads
    travel less vertically than horizontally."""

    sensitivity_x: float = 0.025
    sensitivity_y: float = 0.05
    acceleration: float = 0.5  # 0 = linear; higher damps small movements harder
    motion_threshold_px: float = 0.0  # cursor movement below this is dropped
    yield_resume_after_s: float = 3.0  # quiet period before resuming after a physical-mouse touch
    click_logging_enabled: bool = True  # record fired actions to clicks.log
    dwell_click_enabled: bool = False  # click automatically when the cursor holds still
    dwell_time_s: float = 1.0  # how long it must hold still before the click fires
    keyboard_button_enabled: bool = True  # show the floating virtual-keyboard button
    voice_button_enabled: bool = True  # show the floating voice-typing button


# Accepted range per tuning field, matching the GUI sliders. Values are
# clamped on load: a hand-edited negative acceleration would otherwise raise
# ZeroDivisionError inside the acceleration curve on the first still frame
# and kill the tracking thread.
CALIBRATION_RANGES = {
    "sensitivity_x": (0.005, 0.10),
    "sensitivity_y": (0.005, 0.10),
    "acceleration": (0.0, 1.0),
    "motion_threshold_px": (0.0, 10.0),
    "yield_resume_after_s": (1.0, 10.0),
    "dwell_time_s": (0.3, 5.0),
}


def _clamped(raw_cal: dict, field: str, fallback: float) -> float:
    low, high = CALIBRATION_RANGES[field]
    try:
        value = float(raw_cal.get(field, fallback))
    except (TypeError, ValueError):
        value = fallback
    return max(low, min(high, value))


@dataclass
class ActionButtonsConfig:
    """Screen position of the floating keyboard+mic button group, in pixels
    (top-left corner). `None` means "never dragged" -- the group falls back
    to its default bottom-right corner (see action_buttons.py). The two
    buttons move as one unit, so there is only one saved position for both."""

    x: float | None = None
    y: float | None = None


@dataclass
class CursorConfig:
    """The real Windows Arrow cursor's theme. size_px==32 and mode=="default"
    together mean "untouched" -- see cursor_theme.apply_cursor's no-op
    guard, which this config's defaults are built to trigger."""

    size_px: int = 32
    mode: str = "default"
    custom_color: str = "#000000"


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamped_cursor_size(raw_cursor: dict, fallback: int) -> int:
    low, high = CURSOR_SIZE_RANGE
    try:
        value = int(raw_cursor.get("size_px", fallback))
    except (TypeError, ValueError):
        value = fallback
    return max(low, min(high, value))


def cursor_from_dict(raw_cursor: dict) -> CursorConfig:
    """Public (unlike `_merge_gesture`) because backend.py's
    `_cmd_set_cursor_theme` (Task 4) calls this directly with a single
    command's fields, not just from `config_from_dict`'s full-document
    parse -- both need the exact same clamp/fallback rules."""
    default = CursorConfig()
    mode = raw_cursor.get("mode", default.mode)
    if mode not in VALID_CURSOR_MODES:
        mode = default.mode
    custom_color = raw_cursor.get("custom_color", default.custom_color)
    if not isinstance(custom_color, str):
        custom_color = default.custom_color
    return CursorConfig(
        size_px=_clamped_cursor_size(raw_cursor, default.size_px),
        mode=mode,
        custom_color=custom_color,
    )


@dataclass
class GestureConfig:
    action: str = "none"
    threshold: float = 0.2
    cooldown_ms: int = 400
    hold_ms: int = 400


@dataclass
class AppConfig:
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    gestures: dict = field(default_factory=dict)
    action_buttons: ActionButtonsConfig = field(default_factory=ActionButtonsConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)


def default_config() -> AppConfig:
    gestures = {
        name: GestureConfig(
            action=DEFAULT_ACTIONS[name],
            threshold=DEFAULT_THRESHOLDS[name],
            cooldown_ms=DEFAULT_COOLDOWN_MS[name],
            hold_ms=DEFAULT_HOLD_MS[name],
        )
        for name in GESTURE_NAMES
    }
    return AppConfig(calibration=CalibrationConfig(), gestures=gestures)


def _merge_gesture(name: str, raw: dict) -> GestureConfig:
    base = GestureConfig(
        action=DEFAULT_ACTIONS[name],
        threshold=DEFAULT_THRESHOLDS[name],
        cooldown_ms=DEFAULT_COOLDOWN_MS[name],
        hold_ms=DEFAULT_HOLD_MS[name],
    )
    action = raw.get("action", base.action)
    if action not in VALID_ACTIONS:
        action = base.action
    return GestureConfig(
        action=action,
        threshold=float(raw.get("threshold", base.threshold)),
        cooldown_ms=int(raw.get("cooldown_ms", base.cooldown_ms)),
        hold_ms=int(raw.get("hold_ms", base.hold_ms)),
    )


def config_to_dict(config: AppConfig) -> dict:
    return {
        "calibration": asdict(config.calibration),
        "gestures": {name: asdict(cfg) for name, cfg in config.gestures.items()},
        "action_buttons": asdict(config.action_buttons),
        "cursor": asdict(config.cursor),
    }


def config_from_dict(raw: dict) -> AppConfig:
    default = default_config()
    # Pre-optical-flow keys (x_min, x_max, y_min, y_max, smoothing,
    # deadzone_px, sensitivity) are simply not read here, so they fall away
    # on the next save. No migration is attempted: four-point calibration
    # bounds have no sensitivity equivalent to convert to.
    raw_cal = raw.get("calibration", {})
    click_logging_enabled = raw_cal.get(
        "click_logging_enabled", default.calibration.click_logging_enabled
    )
    if not isinstance(click_logging_enabled, bool):
        click_logging_enabled = default.calibration.click_logging_enabled
    dwell_click_enabled = raw_cal.get(
        "dwell_click_enabled", default.calibration.dwell_click_enabled
    )
    if not isinstance(dwell_click_enabled, bool):
        dwell_click_enabled = default.calibration.dwell_click_enabled
    keyboard_button_enabled = raw_cal.get(
        "keyboard_button_enabled", default.calibration.keyboard_button_enabled
    )
    if not isinstance(keyboard_button_enabled, bool):
        keyboard_button_enabled = default.calibration.keyboard_button_enabled
    voice_button_enabled = raw_cal.get(
        "voice_button_enabled", default.calibration.voice_button_enabled
    )
    if not isinstance(voice_button_enabled, bool):
        voice_button_enabled = default.calibration.voice_button_enabled
    calibration = CalibrationConfig(
        sensitivity_x=_clamped(raw_cal, "sensitivity_x", default.calibration.sensitivity_x),
        sensitivity_y=_clamped(raw_cal, "sensitivity_y", default.calibration.sensitivity_y),
        acceleration=_clamped(raw_cal, "acceleration", default.calibration.acceleration),
        motion_threshold_px=_clamped(
            raw_cal, "motion_threshold_px", default.calibration.motion_threshold_px
        ),
        yield_resume_after_s=_clamped(
            raw_cal, "yield_resume_after_s", default.calibration.yield_resume_after_s
        ),
        click_logging_enabled=click_logging_enabled,
        dwell_click_enabled=dwell_click_enabled,
        dwell_time_s=_clamped(raw_cal, "dwell_time_s", default.calibration.dwell_time_s),
        keyboard_button_enabled=keyboard_button_enabled,
        voice_button_enabled=voice_button_enabled,
    )

    raw_gestures = dict(raw.get("gestures", {}))
    for legacy_name, current_name in LEGACY_GESTURE_NAMES.items():
        if legacy_name in raw_gestures and current_name not in raw_gestures:
            raw_gestures[current_name] = raw_gestures[legacy_name]

    gestures = {
        name: _merge_gesture(name, raw_gestures.get(name, {}))
        for name in GESTURE_NAMES
    }

    raw_buttons = raw.get("action_buttons", {})
    action_buttons = ActionButtonsConfig(
        x=_optional_float(raw_buttons.get("x")),
        y=_optional_float(raw_buttons.get("y")),
    )

    cursor = cursor_from_dict(raw.get("cursor", {}))

    return AppConfig(
        calibration=calibration,
        gestures=gestures,
        action_buttons=action_buttons,
        cursor=cursor,
    )


def load_config(path: str | Path) -> AppConfig:
    """Loads config from `path`, filling in defaults for missing fields.

    Falls back to a full default config if the file is missing or invalid.
    """
    path = Path(path)
    if not path.exists():
        return default_config()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return default_config()

    return config_from_dict(raw)


def save_config(path: str | Path, config: AppConfig) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config_to_dict(config), indent=2), encoding="utf-8")
