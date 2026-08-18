import { describe, expect, it, vi, beforeEach } from "vitest";
import { EventEmitter } from "node:events";

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
vi.mock("../src/main/ipcRelay", () => ({ mainRelay: new EventEmitter() }));

describe("buttons:drag-move", () => {
  beforeEach(() => {
    vi.resetModules();
    FakeBrowserWindow.instances = [];
  });

  it("moves the window by the given delta", async () => {
    const { createButtonsWindow } = await import("../src/main/windows/buttonsWindow");
    const { mainRelay } = await import("../src/main/ipcRelay");
    createButtonsWindow({ send: vi.fn() } as never, null, null);

    mainRelay.emit("buttons:drag-move", { dx: 5, dy: -3 });

    expect(FakeBrowserWindow.instances[0].setPosition).toHaveBeenCalledWith(105, 197);
  });

  it("ignores a malformed delta instead of crashing the main process", async () => {
    // Regression test: a NaN/undefined delta (dx or dy missing or not a
    // number) used to be handed straight to win.setPosition(), which
    // throws synchronously out of the mainRelay.emit() call and takes the
    // whole main process down -- the same failure shape as the
    // ipcMain.emit bug fixed earlier, one step further down the chain.
    const { createButtonsWindow } = await import("../src/main/windows/buttonsWindow");
    const { mainRelay } = await import("../src/main/ipcRelay");
    createButtonsWindow({ send: vi.fn() } as never, null, null);

    expect(() =>
      mainRelay.emit("buttons:drag-move", { dx: undefined, dy: 5 })
    ).not.toThrow();

    expect(FakeBrowserWindow.instances[0].setPosition).not.toHaveBeenCalled();
  });
});
