import { BrowserWindow, ipcMain } from "electron";
import { BackendProcess } from "../services/backendProcess";

export function wireBackendRelay(backend: BackendProcess): void {
  backend.on("message", (message: { type: string }) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send(`backend:${message.type}`, message);
    }
  });
  ipcMain.on("backend:send", (_event, message: { type: string }) => {
    if (message.type.includes(":")) {
      // Namespaced types (config:*, buttons:*) are main-process-only --
      // re-emit on ipcMain itself so the ipc/*.ipc.ts module that owns
      // that namespace can listen for it directly, instead of every
      // listener filtering the shared channel.
      ipcMain.emit(message.type, undefined, message);
      return;
    }
    backend.send(message);
  });
}
