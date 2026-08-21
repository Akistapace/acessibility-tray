import { BrowserWindow, ipcMain } from "electron";
import { EventEmitter } from "node:events";
import type { BackendServer } from "../services/backendServer";

// Namespaced command types (config:*, buttons:*) are main-process-only --
// the ipc/*.ipc.ts module that owns that namespace listens here directly
// instead of every listener filtering the shared "backend:send" channel.
// This has to be a plain EventEmitter rather than ipcMain itself: ipcMain's
// `emit` is not a plain Node EventEmitter -- Electron gives it native
// argument marshaling meant for real renderer-originated IPC events, and it
// crashes the whole main process ("conversion failure") when fed a
// synthetic emit call.
export const mainRelay = new EventEmitter();

export function wireBackendRelay(backend: BackendServer): void {
  backend.on("message", (message: { type: string }) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send(`backend:${message.type}`, message);
    }
  });
  ipcMain.on("backend:send", (_event, message: { type: string }) => {
    if (message.type.includes(":")) {
      mainRelay.emit(message.type, message);
      return;
    }
    backend.send(message);
  });
}
