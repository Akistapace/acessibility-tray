import { describe, expect, it, vi, beforeEach } from "vitest";

class FakeBrowserWindow {
  static instances: FakeBrowserWindow[] = [];
  on = vi.fn();
  loadFile = vi.fn();
  showInactive = vi.fn();
  hide = vi.fn();
  getPosition = vi.fn(() => [100, 200]);
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

describe("keyboardWindow", () => {
  beforeEach(() => {
    vi.resetModules();
    FakeBrowserWindow.instances = [];
  });

  it("moveKeyboardWindow adds the delta to the current position", async () => {
    const { createKeyboardWindow, moveKeyboardWindow } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send: vi.fn() } as never, null, null);

    moveKeyboardWindow(5, -3);

    expect(FakeBrowserWindow.instances[0].setPosition).toHaveBeenCalledWith(105, 197);
  });

  it("ignores a malformed delta instead of crashing the main process", async () => {
    const { createKeyboardWindow, moveKeyboardWindow } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send: vi.fn() } as never, null, null);

    expect(() => moveKeyboardWindow(undefined as unknown as number, 5)).not.toThrow();

    expect(FakeBrowserWindow.instances[0].setPosition).not.toHaveBeenCalled();
  });

  it("endKeyboardDrag saves the current position through the backend", async () => {
    const send = vi.fn();
    const { createKeyboardWindow, endKeyboardDrag } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send } as never, null, null);

    endKeyboardDrag();

    expect(send).toHaveBeenCalledWith({
      type: "save_config",
      config: { custom_keyboard: { x: 100, y: 200 } },
    });
  });

  it("showKeyboardWindow shows the window without activating it", async () => {
    const { createKeyboardWindow, showKeyboardWindow } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send: vi.fn() } as never, null, null);

    showKeyboardWindow();

    expect(FakeBrowserWindow.instances[0].showInactive).toHaveBeenCalled();
  });

  it("hideKeyboardWindow hides the window", async () => {
    const { createKeyboardWindow, hideKeyboardWindow } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send: vi.fn() } as never, null, null);

    hideKeyboardWindow();

    expect(FakeBrowserWindow.instances[0].hide).toHaveBeenCalled();
  });
});
