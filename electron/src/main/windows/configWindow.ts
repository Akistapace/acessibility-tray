import { BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { BackendProcess } from "../backendProcess";

let win: BrowserWindow | null = null;

export function createConfigWindow(backend: BackendProcess): BrowserWindow {
  win = new BrowserWindow({
    width: 1060,
    height: 680,
    minWidth: 1000,
    minHeight: 620,
    title: "FaceMesh Mouse",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "config", "index.html"));
  win.on("show", () => backend.send({ type: "set_preview", enabled: true }));
  win.on("hide", () => backend.send({ type: "set_preview", enabled: false }));
  win.on("close", (event) => {
    event.preventDefault();
    win?.hide();
  });
  return win;
}

export function showConfigWindow(): void {
  win?.show();
  win?.focus();
}

ipcMain.on("config:reset-position", () => {
  // Wired to the floating-buttons window in Task 13.
});
