export async function toggleVoiceTyping(): Promise<void> {
  try {
    const { keyboard, Key } = await import("@nut-tree-fork/nut-js");
    await keyboard.pressKey(Key.LeftSuper, Key.H);
    await keyboard.releaseKey(Key.LeftSuper, Key.H);
  } catch (exc) {
    console.error(`facemesh-mouse: could not toggle voice typing (${exc})`);
  }
}
