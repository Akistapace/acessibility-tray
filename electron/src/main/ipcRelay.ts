import { BrowserWindow, ipcMain } from "electron";
import { BackendProcess } from "./backendProcess";

export function wireBackendRelay(backend: BackendProcess): void {
  backend.on("message", (message: { type: string }) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send(`backend:${message.type}`, message);
    }
  });
  ipcMain.on("backend:send", (_event, message) => {
    backend.send(message);
  });
}
