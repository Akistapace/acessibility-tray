import { BrowserWindow, dialog, app } from "electron";
import path from "node:path";
import type { BackendServer } from "../services/backendServer";

export function createTrackingWindow(backend: BackendServer): BrowserWindow {
  // This window is never shown (`show: false`, permanently, by design -- it
  // only hosts the camera/tracking loop). Chromium throttles rAF-driven work
  // to ~1Hz or less for windows that are never shown, so disable background
  // throttling here; the tracking loop itself also switched off
  // requestAnimationFrame to a self-scheduling setTimeout for the same reason.
  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "tracking", "index.html"));

  // Tracks the last preview-enabled state so a first-run set_preview sent
  // before the renderer finishes loading (and registers its onSetPreview
  // listener) isn't silently lost -- re-sent once did-finish-load fires.
  let lastPreviewEnabled = false;
  win.webContents.once("did-finish-load", () => {
    win.webContents.send("tracking:set-preview", lastPreviewEnabled);
  });

  backend.onPreviewChange((enabled) => {
    lastPreviewEnabled = enabled;
    win.webContents.send("tracking:set-preview", enabled);
  });

  // The tracking renderer plays the same role the deleted stdio backend
  // process used to: if it dies (GPU process loss, WASM OOM, etc.) the app
  // would otherwise sit with a dead tracking loop behind it and no cursor
  // control, with nothing telling the user why. Surface it the same way the
  // camera-open failure in main/index.ts does.
  win.webContents.on("render-process-gone", (_event, details) => {
    dialog.showErrorBox(
      "FaceMesh Mouse",
      `O processo de rastreamento foi encerrado inesperadamente (${details.reason}). O aplicativo será fechado.`
    );
    app.quit();
  });

  return win;
}
