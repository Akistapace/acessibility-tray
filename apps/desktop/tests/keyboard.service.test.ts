import { describe, expect, it, vi, beforeEach } from "vitest";

const typeMock = vi.fn();
const pressKeyMock = vi.fn();
const releaseKeyMock = vi.fn();

vi.mock("@nut-tree-fork/nut-js", () => ({
  keyboard: { type: typeMock, pressKey: pressKeyMock, releaseKey: releaseKeyMock, config: {} },
  Key: { Backspace: "Backspace", Return: "Return" },
}));

import { typeText, pressBackspace, pressEnter } from "../src/main/services/keyboard.service";

describe("keyboard.service custom-keyboard helpers", () => {
  beforeEach(() => {
    typeMock.mockClear();
    pressKeyMock.mockClear();
    releaseKeyMock.mockClear();
  });

  it("typeText types the given text through nut-js", async () => {
    await typeText("á");
    expect(typeMock).toHaveBeenCalledWith("á");
  });

  it("pressBackspace presses and releases Backspace", async () => {
    await pressBackspace();
    expect(pressKeyMock).toHaveBeenCalledWith("Backspace");
    expect(releaseKeyMock).toHaveBeenCalledWith("Backspace");
  });

  it("pressEnter presses and releases Return (the main Enter key, not numpad Enter)", async () => {
    await pressEnter();
    expect(pressKeyMock).toHaveBeenCalledWith("Return");
    expect(releaseKeyMock).toHaveBeenCalledWith("Return");
  });

  it("typeText swallows a nut-js failure instead of throwing", async () => {
    typeMock.mockRejectedValueOnce(new Error("boom"));
    await expect(typeText("x")).resolves.toBeUndefined();
  });
});
