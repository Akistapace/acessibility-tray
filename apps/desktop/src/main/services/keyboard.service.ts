export async function toggleVoiceTyping(): Promise<void> {
  try {
    const { keyboard, Key } = await import("@nut-tree-fork/nut-js");
    keyboard.config.autoDelayMs = 10;
    await keyboard.pressKey(Key.LeftSuper, Key.H);
    await keyboard.releaseKey(Key.LeftSuper, Key.H);
  } catch (exc) {
    console.error(`facemesh-mouse: could not toggle voice typing (${exc})`);
  }
}

export async function typeText(text: string): Promise<void> {
  try {
    const { keyboard } = await import("@nut-tree-fork/nut-js");
    keyboard.config.autoDelayMs = 10;
    await keyboard.type(text);
  } catch (exc) {
    console.error(`facemesh-mouse: could not type text (${exc})`);
  }
}

export async function pressBackspace(): Promise<void> {
  try {
    const { keyboard, Key } = await import("@nut-tree-fork/nut-js");
    keyboard.config.autoDelayMs = 10;
    await keyboard.pressKey(Key.Backspace);
    await keyboard.releaseKey(Key.Backspace);
  } catch (exc) {
    console.error(`facemesh-mouse: could not press backspace (${exc})`);
  }
}

export async function pressEnter(): Promise<void> {
  try {
    const { keyboard, Key } = await import("@nut-tree-fork/nut-js");
    keyboard.config.autoDelayMs = 10;
    // Key.Return is the main keyboard's Enter key; Key.Enter is numpad Enter.
    await keyboard.pressKey(Key.Return);
    await keyboard.releaseKey(Key.Return);
  } catch (exc) {
    console.error(`facemesh-mouse: could not press enter (${exc})`);
  }
}
