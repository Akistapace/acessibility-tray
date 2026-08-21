interface ConfigLike {
  calibration?: {
    keyboard_button_enabled?: boolean;
    voice_button_enabled?: boolean;
  };
}

// Absent config (nothing received yet) and an absent flag on a received
// config both mean "enabled" -- only an explicit false hides the button.
export function isKeyboardButtonEnabled(config: ConfigLike | null | undefined): boolean {
  return config?.calibration?.keyboard_button_enabled !== false;
}

export function isVoiceButtonEnabled(config: ConfigLike | null | undefined): boolean {
  return config?.calibration?.voice_button_enabled !== false;
}
