import { describe, expect, it, vi, beforeEach } from "vitest";

class FakeBrowserWindow {
  static instances: FakeBrowserWindow[] = [];
  on = vi.fn();
  loadFile = vi.fn();
  showInactive = vi.fn();
  getPosition = vi.fn(() => [100, 200]);
  setPosition = vi.fn();

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
