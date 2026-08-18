import { describe, expect, it, vi, beforeEach } from "vitest";

class FakeBrowserWindow {
  static instances: FakeBrowserWindow[] = [];
  destroyed = false;
  on = vi.fn();
  loadFile = vi.fn();
  show = vi.fn(() => {
    if (this.destroyed) throw new TypeError("Object has been destroyed");
  });
  focus = vi.fn(() => {
    if (this.destroyed) throw new TypeError("Object has been destroyed");
  });
  isDestroyed = () => this.destroyed;

  constructor() {
    FakeBrowserWindow.instances.push(this);
  }
}

vi.mock("electron", () => ({
  app: { on: vi.fn() },
  BrowserWindow: FakeBrowserWindow,
}));
vi.mock("../src/main/ipcRelay", () => ({ mainRelay: { on: vi.fn() } }));
vi.mock("../src/main/windows/buttonsWindow", () => ({ resetButtonsPosition: vi.fn() }));

describe("showConfigWindow", () => {
  beforeEach(() => {
    vi.resetModules();
    FakeBrowserWindow.instances = [];
  });

  it("reuses the existing window when it is still alive", async () => {
    const { createConfigWindow, showConfigWindow } = await import("../src/main/windows/configWindow");
    createConfigWindow({ send: vi.fn() } as never);

    showConfigWindow();

    expect(FakeBrowserWindow.instances).toHaveLength(1);
    expect(FakeBrowserWindow.instances[0].show).toHaveBeenCalledTimes(1);
    expect(FakeBrowserWindow.instances[0].focus).toHaveBeenCalledTimes(1);
  });

  it("recreates the window instead of crashing when it was destroyed", async () => {
    // Regression test: showConfigWindow used to call win.show()/win.focus()
    // on whatever `win` last pointed to with no isDestroyed() check --
    // Electron throws "Object has been destroyed" calling any method on a
    // destroyed BrowserWindow, which crashed the whole main process from
    // the tray click handler, the "Reabrir Config" menu item, and the
    // Ctrl+Alt+O shortcut alike.
    const { createConfigWindow, showConfigWindow } = await import("../src/main/windows/configWindow");
    createConfigWindow({ send: vi.fn() } as never);
    expect(FakeBrowserWindow.instances).toHaveLength(1);
    FakeBrowserWindow.instances[0].destroyed = true;

    expect(() => showConfigWindow()).not.toThrow();

    expect(FakeBrowserWindow.instances).toHaveLength(2);
    expect(FakeBrowserWindow.instances[1].show).toHaveBeenCalledTimes(1);
    expect(FakeBrowserWindow.instances[1].focus).toHaveBeenCalledTimes(1);
  });
});
