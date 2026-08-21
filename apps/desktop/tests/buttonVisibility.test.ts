import { describe, expect, it } from "vitest";
import { isKeyboardButtonEnabled, isVoiceButtonEnabled } from "../src/renderer/buttons/buttonVisibility";

describe("isKeyboardButtonEnabled / isVoiceButtonEnabled", () => {
  it("treats undefined config as enabled", () => {
    expect(isKeyboardButtonEnabled(undefined)).toBe(true);
    expect(isVoiceButtonEnabled(undefined)).toBe(true);
  });

  it("treats null config as enabled", () => {
    expect(isKeyboardButtonEnabled(null)).toBe(true);
    expect(isVoiceButtonEnabled(null)).toBe(true);
  });

  it("treats a config with no calibration key as enabled", () => {
    expect(isKeyboardButtonEnabled({})).toBe(true);
    expect(isVoiceButtonEnabled({})).toBe(true);
  });

  it("disables the keyboard button only when explicitly false, leaving voice unaffected", () => {
    const config = { calibration: { keyboard_button_enabled: false } };
    expect(isKeyboardButtonEnabled(config)).toBe(false);
    expect(isVoiceButtonEnabled(config)).toBe(true);
  });

  it("disables the voice button only when explicitly false, leaving keyboard unaffected", () => {
    const config = { calibration: { voice_button_enabled: false } };
    expect(isVoiceButtonEnabled(config)).toBe(false);
    expect(isKeyboardButtonEnabled(config)).toBe(true);
  });

  it("keeps both enabled when both are explicitly true", () => {
    const config = { calibration: { keyboard_button_enabled: true, voice_button_enabled: true } };
    expect(isKeyboardButtonEnabled(config)).toBe(true);
    expect(isVoiceButtonEnabled(config)).toBe(true);
  });
});
