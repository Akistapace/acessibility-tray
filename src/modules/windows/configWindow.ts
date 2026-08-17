import { app, BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { BackendProcess } from "../backendProcess";
import { resetButtonsPosition } from "./buttonsWindow";

let win: BrowserWindow | null = null;

// The close handler below cancels every close so the X button only hides
// the window (the app lives in the tray). That would also cancel the
// closes app.quit() issues, leaving a zombie app with a dead backend, so
// track quitting here. Listening to before-quit ourselves -- rather than
// importing a flag from index.ts -- keeps the dependency one-way:
// index.ts already imports from this module.
let isQuitting = false;
app.on("before-quit", () => {
  isQuitting = true;
});

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
    if (isQuitting) return;
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
  resetButtonsPosition();
});
