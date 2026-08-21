import { describe, expect, it } from "vitest";
import { isKeyboardButtonEnabled, isVoiceButtonEnabled } from "../src/renderer/buttons/buttonVisibility";

describe("isKeyboardButtonEnabled", () => {
  it("is enabled by default before any config has arrived", () => {
    expect(isKeyboardButtonEnabled(null)).toBe(true);
    expect(isKeyboardButtonEnabled(undefined)).toBe(true);
  });

  it("is enabled when the config doesn't mention the flag", () => {
    expect(isKeyboardButtonEnabled({ calibration: {} })).toBe(true);
  });

  it("is enabled when the flag is explicitly true", () => {
    expect(isKeyboardButtonEnabled({ calibration: { keyboard_button_enabled: true } })).toBe(true);
  });

  it("is disabled only when the flag is explicitly false", () => {
    expect(isKeyboardButtonEnabled({ calibration: { keyboard_button_enabled: false } })).toBe(false);
  });
});

describe("isVoiceButtonEnabled", () => {
  it("is enabled by default before any config has arrived", () => {
    expect(isVoiceButtonEnabled(null)).toBe(true);
    expect(isVoiceButtonEnabled(undefined)).toBe(true);
  });

  it("is enabled when the config doesn't mention the flag", () => {
    expect(isVoiceButtonEnabled({ calibration: {} })).toBe(true);
  });

  it("is enabled when the flag is explicitly true", () => {
    expect(isVoiceButtonEnabled({ calibration: { voice_button_enabled: true } })).toBe(true);
  });

  it("is disabled only when the flag is explicitly false", () => {
    expect(isVoiceButtonEnabled({ calibration: { voice_button_enabled: false } })).toBe(false);
  });

  it("is independent of the keyboard flag", () => {
    expect(
      isVoiceButtonEnabled({ calibration: { keyboard_button_enabled: false, voice_button_enabled: true } })
    ).toBe(true);
  });
});
