import { BrowserWindow } from "electron";
import path from "node:path";
import type { BackendServer } from "../services/backendServer";

export function createTrackingWindow(backend: BackendServer): BrowserWindow {
  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "tracking", "index.html"));

  backend.onPreviewChange((enabled) => {
    win.webContents.send("tracking:set-preview", enabled);
  });

  return win;
}
