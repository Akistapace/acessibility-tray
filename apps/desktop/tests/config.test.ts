import { describe, expect, it, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import * as configMod from "../src/main/services/config.service";

let tmpDir: string;
beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "facemesh-config-"));
});
afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("defaultConfig", () => {
  it("has all nine gestures", () => {
    const cfg = configMod.defaultConfig();
    expect(new Set(Object.keys(cfg.gestures))).toEqual(new Set(configMod.GESTURE_NAMES));
  });

  it("has the documented tracking defaults", () => {
    const cal = configMod.defaultConfig().calibration;
    expect(cal.sensitivity_x).toBe(0.025);
    expect(cal.sensitivity_y).toBe(0.05);
    expect(cal.acceleration).toBe(0.5);
  });
});

describe("loadConfig", () => {
  it("returns default for a missing file", () => {
    const cfg = configMod.loadConfig(path.join(tmpDir, "does_not_exist.json"));
    expect(cfg.calibration).toEqual(configMod.defaultConfig().calibration);
  });

  it("returns default for invalid JSON", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(file, "{not valid json");
    expect(configMod.loadConfig(file).calibration).toEqual(configMod.defaultConfig().calibration);
  });

  it("merges a partial file with defaults", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(file, JSON.stringify({ gestures: { blink_a: { action: "right_click" } } }));
    const loaded = configMod.loadConfig(file);
    expect(loaded.gestures.blink_a.action).toBe("right_click");
    expect(loaded.gestures.mouth_open.action).toBe(configMod.DEFAULT_ACTIONS.mouth_open);
  });

  it("falls back to the default action for an invalid action value", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(file, JSON.stringify({ gestures: { blink_a: { action: "not_a_real_action" } } }));
    expect(configMod.loadConfig(file).gestures.blink_a.action).toBe(configMod.DEFAULT_ACTIONS.blink_a);
  });

  it("clamps out-of-range calibration values", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(file, JSON.stringify({ calibration: { acceleration: -5, sensitivity_x: 99 } }));
    const cal = configMod.loadConfig(file).calibration;
    expect(cal.acceleration).toBe(0.0);
    expect(cal.sensitivity_x).toBe(0.1);
  });

  it("falls back to the default for a non-numeric calibration value", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(file, JSON.stringify({ calibration: { acceleration: "fast" } }));
    expect(configMod.loadConfig(file).calibration.acceleration).toBe(0.5);
  });

  it("migrates legacy blink_left/blink_right names", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(
      file,
      JSON.stringify({ gestures: { blink_left: { action: "scroll_up" }, blink_right: { action: "scroll_down" } } })
    );
    const loaded = configMod.loadConfig(file);
    expect(loaded.gestures.blink_a.action).toBe("scroll_up");
    expect(loaded.gestures.blink_b.action).toBe("scroll_down");
  });

  it("does not let a legacy name override an already-migrated config", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(
      file,
      JSON.stringify({
        gestures: { eyebrow_raised: { action: "scroll_up" }, eyebrow_both: { action: "double_click" } },
      })
    );
    expect(configMod.loadConfig(file).gestures.eyebrow_both.action).toBe("double_click");
  });

  it("drops unrecognized action_buttons values to null", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(file, JSON.stringify({ action_buttons: { x: "nope", y: null } }));
    const loaded = configMod.loadConfig(file);
    expect(loaded.action_buttons.x).toBeNull();
    expect(loaded.action_buttons.y).toBeNull();
  });

  it("defaults keyboard_button_enabled and voice_button_enabled to true", () => {
    const cfg = configMod.defaultConfig();
    expect(cfg.calibration.keyboard_button_enabled).toBe(true);
    expect(cfg.calibration.voice_button_enabled).toBe(true);
  });

  it("round-trips explicit false for keyboard_button_enabled/voice_button_enabled", () => {
    const original = configMod.defaultConfig();
    original.calibration.keyboard_button_enabled = false;
    original.calibration.voice_button_enabled = false;

    const restored = configMod.configFromDict(configMod.configToDict(original));

    expect(restored.calibration.keyboard_button_enabled).toBe(false);
    expect(restored.calibration.voice_button_enabled).toBe(false);
  });

  it("falls back to default for a non-boolean keyboard_button_enabled/voice_button_enabled", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(
      file,
      JSON.stringify({ calibration: { keyboard_button_enabled: "yes", voice_button_enabled: 1 } })
    );
    const cal = configMod.loadConfig(file).calibration;
    expect(cal.keyboard_button_enabled).toBe(true);
    expect(cal.voice_button_enabled).toBe(true);
  });
});

describe("save/load round trip", () => {
  it("round-trips calibration and gesture edits", () => {
    const file = path.join(tmpDir, "config.json");
    const original = configMod.defaultConfig();
    original.calibration.sensitivity_x = 0.04;
    original.gestures.mouth_open.action = "scroll_down";

    configMod.saveConfig(file, original);
    const loaded = configMod.loadConfig(file);

    expect(loaded.calibration.sensitivity_x).toBe(0.04);
    expect(loaded.gestures.mouth_open.action).toBe("scroll_down");
  });

  it("round-trips through configToDict/configFromDict", () => {
    const original = configMod.defaultConfig();
    original.calibration.sensitivity_x = 0.04;
    original.action_buttons.x = 12.0;

    const restored = configMod.configFromDict(configMod.configToDict(original));

    expect(restored.calibration.sensitivity_x).toBe(0.04);
    expect(restored.action_buttons.x).toBe(12.0);
  });
});
