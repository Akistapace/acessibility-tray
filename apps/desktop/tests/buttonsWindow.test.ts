import { describe, expect, it, vi, beforeEach } from "vitest";

class FakeBrowserWindow {
  static instances: FakeBrowserWindow[] = [];
  on = vi.fn();
  loadFile = vi.fn();
  showInactive = vi.fn();
  getPosition = vi.fn(() => [100, 200]);
  // Mirrors Electron's real native setPosition: throws
  // "Error processing argument at index 0, conversion failure" when given
  // a non-finite value (e.g. NaN from a malformed delta), instead of
  // silently coercing it.
  setPosition = vi.fn((x: number, y: number) => {
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      throw new TypeError("Error processing argument at index 0, conversion failure from");
    }
  });

  constructor() {
    FakeBrowserWindow.instances.push(this);
  }
}

vi.mock("electron", () => ({
  BrowserWindow: FakeBrowserWindow,
  screen: {
    getPrimaryDisplay: () => ({
      bounds: { width: 1920, height: 1080 },
      workArea: { height: 1040 },
    }),
  },
}));

describe("buttonsWindow", () => {
  beforeEach(() => {
    vi.resetModules();
    FakeBrowserWindow.instances = [];
  });

  it("moveButtonsWindow adds the delta to the current position", async () => {
    const { createButtonsWindow, moveButtonsWindow } = await import("../src/main/windows/buttonsWindow");
    createButtonsWindow({ send: vi.fn() } as never, null, null);

    moveButtonsWindow(5, -3);

    expect(FakeBrowserWindow.instances[0].setPosition).toHaveBeenCalledWith(105, 197);
  });

  it("ignores a malformed delta instead of crashing the main process", async () => {
    // Regression test: a NaN/undefined delta (dx or dy missing or not a
    // number) used to be handed straight to win.setPosition(), which
    // throws synchronously and takes the whole main process down -- the
    // same failure shape as the ipcMain.emit bug, one step further down
    // the chain.
    const { createButtonsWindow, moveButtonsWindow } = await import("../src/main/windows/buttonsWindow");
    createButtonsWindow({ send: vi.fn() } as never, null, null);

    expect(() => moveButtonsWindow(undefined as unknown as number, 5)).not.toThrow();

    expect(FakeBrowserWindow.instances[0].setPosition).not.toHaveBeenCalled();
  });

  it("endButtonsDrag saves the current position through the backend", async () => {
    const send = vi.fn();
    const { createButtonsWindow, endButtonsDrag } = await import("../src/main/windows/buttonsWindow");
    createButtonsWindow({ send } as never, null, null);

    endButtonsDrag();

    expect(send).toHaveBeenCalledWith({
      type: "save_config",
      config: { action_buttons: { x: 100, y: 200 } },
    });
  });
});
