import { app, BrowserWindow } from "electron";
import path from "node:path";
import type { BackendServer } from "../services/backendServer";

let win: BrowserWindow | null = null;
let backendRef: BackendServer | null = null;

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

function buildWindow(backend: BackendServer): BrowserWindow {
  const window = new BrowserWindow({
    width: 1060,
    height: 680,
    minWidth: 1000,
    minHeight: 620,
    title: "FaceMesh Mouse",
    icon: path.join(__dirname, "..", "..", "assets", "icon.ico"),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  window.loadFile(path.join(__dirname, "..", "..", "renderer", "config", "index.html"));
  window.on("show", () => backend.send({ type: "set_preview", enabled: true }));
  window.on("hide", () => backend.send({ type: "set_preview", enabled: false }));
  window.on("close", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    window.hide();
  });
  return window;
}

export function createConfigWindow(backend: BackendServer): BrowserWindow {
  backendRef = backend;
  win = buildWindow(backend);
  return win;
}

export function showConfigWindow(): void {
  // Electron throws "Object has been destroyed" on any method call once a
  // BrowserWindow is gone -- rebuilding it here instead of crashing the
  // whole main process (see configWindow.test.ts for the reproduction).
  if ((!win || win.isDestroyed()) && backendRef) {
    win = buildWindow(backendRef);
  }
  win?.show();
  win?.focus();
}
