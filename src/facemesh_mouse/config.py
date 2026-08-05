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
    "blink_left",
    "blink_right",
    "blink_both",
    "mouth_open",
    "eyebrow_raised",
]

DEFAULT_THRESHOLDS = {
    "blink_left": 0.21,
    "blink_right": 0.21,
    "blink_both": 0.21,
    "mouth_open": 0.35,
    "eyebrow_raised": 0.15,
}

DEFAULT_ACTIONS = {
    "blink_left": "left_click",
    "blink_right": "right_click",
    "blink_both": "none",
    "mouth_open": "double_click",
    "eyebrow_raised": "scroll_up",
}

DEFAULT_COOLDOWN_MS = {
    "blink_left": 400,
    "blink_right": 400,
    "blink_both": 400,
    "mouth_open": 600,
    "eyebrow_raised": 300,
}


@dataclass
class CalibrationConfig:
    x_min: float = 0.35
    x_max: float = 0.65
    y_min: float = 0.35
    y_max: float = 0.65
    smoothing: float = 0.7  # weight kept from the previous smoothed sample


@dataclass
class GestureConfig:
    action: str = "none"
    threshold: float = 0.2
    cooldown_ms: int = 400


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
        )
        for name in GESTURE_NAMES
    }
    return AppConfig(calibration=CalibrationConfig(), gestures=gestures)


def _merge_gesture(name: str, raw: dict) -> GestureConfig:
    base = GestureConfig(
        action=DEFAULT_ACTIONS[name],
        threshold=DEFAULT_THRESHOLDS[name],
        cooldown_ms=DEFAULT_COOLDOWN_MS[name],
    )
    action = raw.get("action", base.action)
    if action not in VALID_ACTIONS:
        action = base.action
    return GestureConfig(
        action=action,
        threshold=float(raw.get("threshold", base.threshold)),
        cooldown_ms=int(raw.get("cooldown_ms", base.cooldown_ms)),
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
    )

    raw_gestures = raw.get("gestures", {})
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
