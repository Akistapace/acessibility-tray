import fs from "node:fs";
import path from "node:path";
import { VALID_CURSOR_MODES } from "./cursorImage";

export const VALID_ACTIONS = new Set([
  "none",
  "left_click",
  "right_click",
  "double_click",
  "scroll_up",
  "scroll_down",
  "left_drag",
  "freeze_cursor",
]);

export const GESTURE_NAMES = [
  "blink_a",
  "blink_b",
  "blink_both",
  "eyebrow_a",
  "eyebrow_b",
  "eyebrow_both",
  "mouth_open",
  "mouth_left",
  "mouth_right",
] as const;

export type GestureName = (typeof GESTURE_NAMES)[number];

export const LEGACY_GESTURE_NAMES: Record<string, GestureName> = {
  blink_left: "blink_a",
  blink_right: "blink_b",
  eyebrow_raised: "eyebrow_both",
};

export const DEFAULT_THRESHOLDS: Record<GestureName, number> = {
  blink_a: 0.21, blink_b: 0.21, blink_both: 0.21,
  eyebrow_a: 0.15, eyebrow_b: 0.15, eyebrow_both: 0.15,
  mouth_open: 0.35, mouth_left: 0.05, mouth_right: 0.05,
};

export const DEFAULT_ACTIONS: Record<GestureName, string> = {
  blink_a: "left_click", blink_b: "right_click", blink_both: "none",
  eyebrow_a: "none", eyebrow_b: "none", eyebrow_both: "none",
  mouth_open: "double_click", mouth_left: "none", mouth_right: "none",
};

export const DEFAULT_COOLDOWN_MS: Record<GestureName, number> = {
  blink_a: 400, blink_b: 400, blink_both: 400,
  eyebrow_a: 400, eyebrow_b: 400, eyebrow_both: 400,
  mouth_open: 600, mouth_left: 400, mouth_right: 400,
};

export const DEFAULT_HOLD_MS: Record<GestureName, number> = Object.fromEntries(
  GESTURE_NAMES.map((name) => [name, 400])
) as Record<GestureName, number>;

export interface CalibrationConfig {
  sensitivity_x: number;
  sensitivity_y: number;
  acceleration: number;
  motion_threshold_px: number;
  yield_resume_after_s: number;
  click_logging_enabled: boolean;
  dwell_click_enabled: boolean;
  dwell_time_s: number;
  keyboard_button_enabled: boolean;
  voice_button_enabled: boolean;
}

export const CALIBRATION_RANGES: Record<string, [number, number]> = {
  sensitivity_x: [0.005, 0.10],
  sensitivity_y: [0.005, 0.10],
  acceleration: [0.0, 1.0],
  motion_threshold_px: [0.0, 10.0],
  yield_resume_after_s: [1.0, 10.0],
  dwell_time_s: [0.3, 5.0],
};

function defaultCalibration(): CalibrationConfig {
  return {
    sensitivity_x: 0.025,
    sensitivity_y: 0.05,
    acceleration: 0.5,
    motion_threshold_px: 0.0,
    yield_resume_after_s: 3.0,
    click_logging_enabled: true,
    dwell_click_enabled: false,
    dwell_time_s: 1.0,
    keyboard_button_enabled: true,
    voice_button_enabled: true,
  };
}

function clamped(rawCal: Record<string, unknown>, field: string, fallback: number): number {
  const [low, high] = CALIBRATION_RANGES[field];
  const raw = rawCal[field];
  const num = typeof raw === "number" || typeof raw === "string" ? Number(raw) : NaN;
  const resolved = Number.isFinite(num) ? num : fallback;
  return Math.max(low, Math.min(high, resolved));
}

export interface ActionButtonsConfig {
  x: number | null;
  y: number | null;
}

export interface CustomKeyboardConfig {
  x: number | null;
  y: number | null;
  compact: boolean;
}

function optionalFloat(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

export interface GestureConfig {
  action: string;
  threshold: number;
  cooldown_ms: number;
  hold_ms: number;
}

export const CURSOR_SIZE_RANGE: [number, number] = [32, 96];

export interface CursorConfig {
  size_px: number;
  mode: string;
  custom_color: string;
}

function defaultCursor(): CursorConfig {
  return { size_px: 32, mode: "default", custom_color: "#000000" };
}

function clampedCursorSize(rawCursor: Record<string, unknown>, fallback: number): number {
  const [low, high] = CURSOR_SIZE_RANGE;
  const raw = rawCursor.size_px;
  const num = typeof raw === "number" || typeof raw === "string" ? Number(raw) : NaN;
  const resolved = Number.isFinite(num) ? Math.trunc(num) : fallback;
  return Math.max(low, Math.min(high, resolved));
}

// Exported (unlike the internal mergeGesture) because BackendServer's
// set_cursor_theme handler calls this directly with a single command's
// fields, not just from configFromDict's full-document parse -- both need
// the exact same clamp/fallback rules.
export function cursorFromDict(rawCursor: Record<string, unknown>): CursorConfig {
  const fallback = defaultCursor();
  const mode = typeof rawCursor.mode === "string" && VALID_CURSOR_MODES.has(rawCursor.mode) ? rawCursor.mode : fallback.mode;
  const customColor = typeof rawCursor.custom_color === "string" ? rawCursor.custom_color : fallback.custom_color;
  return { size_px: clampedCursorSize(rawCursor, fallback.size_px), mode, custom_color: customColor };
}

export interface AppConfig {
  calibration: CalibrationConfig;
  gestures: Record<string, GestureConfig>;
  action_buttons: ActionButtonsConfig;
  cursor: CursorConfig;
  custom_keyboard: CustomKeyboardConfig;
}

export function defaultConfig(): AppConfig {
  const gestures: Record<string, GestureConfig> = {};
  for (const name of GESTURE_NAMES) {
    gestures[name] = {
      action: DEFAULT_ACTIONS[name],
      threshold: DEFAULT_THRESHOLDS[name],
      cooldown_ms: DEFAULT_COOLDOWN_MS[name],
      hold_ms: DEFAULT_HOLD_MS[name],
    };
  }
  return { calibration: defaultCalibration(), gestures, action_buttons: { x: null, y: null }, cursor: defaultCursor(), custom_keyboard: { x: null, y: null, compact: true } };
}

function mergeGesture(name: GestureName, raw: Record<string, unknown>): GestureConfig {
  const base: GestureConfig = {
    action: DEFAULT_ACTIONS[name],
    threshold: DEFAULT_THRESHOLDS[name],
    cooldown_ms: DEFAULT_COOLDOWN_MS[name],
    hold_ms: DEFAULT_HOLD_MS[name],
  };
  const action = typeof raw.action === "string" && VALID_ACTIONS.has(raw.action) ? raw.action : base.action;
  return {
    action,
    threshold: raw.threshold !== undefined ? Number(raw.threshold) : base.threshold,
    cooldown_ms: raw.cooldown_ms !== undefined ? Math.trunc(Number(raw.cooldown_ms)) : base.cooldown_ms,
    hold_ms: raw.hold_ms !== undefined ? Math.trunc(Number(raw.hold_ms)) : base.hold_ms,
  };
}

export function configToDict(config: AppConfig): Record<string, unknown> {
  return JSON.parse(JSON.stringify(config));
}

export function configFromDict(raw: Record<string, unknown>): AppConfig {
  const fallback = defaultConfig();
  const rawCal = (raw.calibration as Record<string, unknown>) ?? {};

  const clickLoggingRaw = rawCal.click_logging_enabled;
  const click_logging_enabled = typeof clickLoggingRaw === "boolean" ? clickLoggingRaw : fallback.calibration.click_logging_enabled;

  const dwellRaw = rawCal.dwell_click_enabled;
  const dwell_click_enabled = typeof dwellRaw === "boolean" ? dwellRaw : fallback.calibration.dwell_click_enabled;

  const keyboardButtonRaw = rawCal.keyboard_button_enabled;
  const keyboard_button_enabled = typeof keyboardButtonRaw === "boolean" ? keyboardButtonRaw : fallback.calibration.keyboard_button_enabled;

  const voiceButtonRaw = rawCal.voice_button_enabled;
  const voice_button_enabled = typeof voiceButtonRaw === "boolean" ? voiceButtonRaw : fallback.calibration.voice_button_enabled;

  const calibration: CalibrationConfig = {
    sensitivity_x: clamped(rawCal, "sensitivity_x", fallback.calibration.sensitivity_x),
    sensitivity_y: clamped(rawCal, "sensitivity_y", fallback.calibration.sensitivity_y),
    acceleration: clamped(rawCal, "acceleration", fallback.calibration.acceleration),
    motion_threshold_px: clamped(rawCal, "motion_threshold_px", fallback.calibration.motion_threshold_px),
    yield_resume_after_s: clamped(rawCal, "yield_resume_after_s", fallback.calibration.yield_resume_after_s),
    click_logging_enabled,
    dwell_click_enabled,
    dwell_time_s: clamped(rawCal, "dwell_time_s", fallback.calibration.dwell_time_s),
    keyboard_button_enabled,
    voice_button_enabled,
  };

  const rawGestures: Record<string, Record<string, unknown>> = {
    ...((raw.gestures as Record<string, Record<string, unknown>>) ?? {}),
  };
  for (const [legacyName, currentName] of Object.entries(LEGACY_GESTURE_NAMES)) {
    if (rawGestures[legacyName] && !rawGestures[currentName]) {
      rawGestures[currentName] = rawGestures[legacyName];
    }
  }

  const gestures: Record<string, GestureConfig> = {};
  for (const name of GESTURE_NAMES) {
    gestures[name] = mergeGesture(name, rawGestures[name] ?? {});
  }

  const rawButtons = (raw.action_buttons as Record<string, unknown>) ?? {};
  const action_buttons: ActionButtonsConfig = {
    x: optionalFloat(rawButtons.x),
    y: optionalFloat(rawButtons.y),
  };

  const rawKeyboard = (raw.custom_keyboard as Record<string, unknown>) ?? {};
  const compactRaw = rawKeyboard.compact;
  const custom_keyboard: CustomKeyboardConfig = {
    x: optionalFloat(rawKeyboard.x),
    y: optionalFloat(rawKeyboard.y),
    compact: typeof compactRaw === "boolean" ? compactRaw : fallback.custom_keyboard.compact,
  };

  const cursor = cursorFromDict((raw.cursor as Record<string, unknown>) ?? {});

  return { calibration, gestures, action_buttons, cursor, custom_keyboard };
}

export function loadConfig(filePath: string): AppConfig {
  if (!fs.existsSync(filePath)) return defaultConfig();
  let raw: unknown;
  try {
    raw = JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return defaultConfig();
  }
  if (typeof raw !== "object" || raw === null) return defaultConfig();
  return configFromDict(raw as Record<string, unknown>);
}

export function saveConfig(filePath: string, config: AppConfig): void {
  fs.mkdirSync(path.dirname(path.resolve(filePath)), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(configToDict(config), null, 2), "utf-8");
}
