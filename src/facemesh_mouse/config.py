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
}

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
    x_min: float = 0.35
    x_max: float = 0.65
    y_min: float = 0.35
    y_max: float = 0.65
    smoothing: float = 0.7  # weight kept from the previous smoothed sample
    deadzone_px: float = 4.0  # ignore scaled movement below this many screen pixels
    sensitivity: float = 1.0  # multiplier on the calibration-derived cursor scale


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


def load_config(path: str | Path) -> AppConfig:
    """Loads config from `path`, filling in defaults for missing fields.

    Falls back to a full default config if the file is missing or invalid.
    """
    path = Path(path)
    if not path.exists():
        return default_config()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_config()

    default = default_config()
    raw_cal = raw.get("calibration", {})
    calibration = CalibrationConfig(
        x_min=float(raw_cal.get("x_min", default.calibration.x_min)),
        x_max=float(raw_cal.get("x_max", default.calibration.x_max)),
        y_min=float(raw_cal.get("y_min", default.calibration.y_min)),
        y_max=float(raw_cal.get("y_max", default.calibration.y_max)),
        smoothing=float(raw_cal.get("smoothing", default.calibration.smoothing)),
        deadzone_px=float(raw_cal.get("deadzone_px", default.calibration.deadzone_px)),
        sensitivity=float(raw_cal.get("sensitivity", default.calibration.sensitivity)),
    )

    raw_gestures = dict(raw.get("gestures", {}))
    for legacy_name, current_name in LEGACY_GESTURE_NAMES.items():
        if legacy_name in raw_gestures and current_name not in raw_gestures:
            raw_gestures[current_name] = raw_gestures[legacy_name]

    gestures = {
        name: _merge_gesture(name, raw_gestures.get(name, {}))
        for name in GESTURE_NAMES
    }

    return AppConfig(calibration=calibration, gestures=gestures)


def save_config(path: str | Path, config: AppConfig) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "calibration": asdict(config.calibration),
        "gestures": {name: asdict(cfg) for name, cfg in config.gestures.items()},
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
