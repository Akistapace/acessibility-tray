import { describe, expect, it, vi } from "vitest";
import { EventEmitter } from "node:events";

const sendMock = vi.fn();
const getAllWindowsMock = vi.fn(() => [{ webContents: { send: sendMock } }]);
const onMock = vi.fn();

vi.mock("electron", () => ({
  ipcMain: { on: onMock },
  BrowserWindow: { getAllWindows: getAllWindowsMock },
}));

describe("wireBackendRelay", () => {
  it("broadcasts backend messages to every window's webContents", async () => {
    const { wireBackendRelay } = await import("../src/main/ipcRelay");
    const backend = new EventEmitter();
    wireBackendRelay(backend as never);

    backend.emit("message", { type: "status", paused: true });

    expect(sendMock).toHaveBeenCalledWith("backend:status", { type: "status", paused: true });
  });

  it("forwards renderer commands to the backend", async () => {
    const { wireBackendRelay } = await import("../src/main/ipcRelay");
    const backend = new EventEmitter() as EventEmitter & { send: (m: unknown) => void };
    backend.send = vi.fn();
    wireBackendRelay(backend);

    const handler = onMock.mock.calls.find(([channel]) => channel === "backend:send")?.[1];
    handler(undefined, { type: "start" });

    expect(backend.send).toHaveBeenCalledWith({ type: "start" });
  });

  it("routes namespaced commands to mainRelay instead of the backend", async () => {
    // Regression test: this used to call ipcMain.emit(type, undefined,
    // message) directly, which crashes the whole main process the moment
    // a real namespaced command (buttons:drag-move, config:reset-position)
    // fires -- ipcMain's emit isn't a plain EventEmitter, it does native
    // argument marshaling that a synthetic call doesn't satisfy.
    const { wireBackendRelay, mainRelay } = await import("../src/main/ipcRelay");
    const backend = new EventEmitter() as EventEmitter & { send: (m: unknown) => void };
    backend.send = vi.fn();
    wireBackendRelay(backend);

    const handler = onMock.mock.calls.find(([channel]) => channel === "backend:send")?.[1];
    const relayListener = vi.fn();
    mainRelay.on("buttons:drag-move", relayListener);

    handler(undefined, { type: "buttons:drag-move", dx: 3, dy: 4 });

    expect(relayListener).toHaveBeenCalledWith({ type: "buttons:drag-move", dx: 3, dy: 4 });
    expect(backend.send).not.toHaveBeenCalled();
  });
});
