import { app, dialog, globalShortcut, Menu, screen } from "electron";
import fs from "node:fs";
import { BackendServer } from "./services/backendServer";
import { TrackingEngine } from "./services/trackingEngine.service";
import { NutJsMouseDriver } from "./services/mouseController.service";
import { loadConfig } from "./services/config.service";
import { applyCursor, restoreCursor } from "./services/cursorTheme.service";
import { toggleTouchKeyboard } from "./services/win32.service";
import * as clickLog from "./services/clickLog.service";
import { toggleVoiceTyping } from "./services/keyboard.service";
import { wireIpc } from "./ipc";
import { createTray } from "./services/tray.service";
import { createConfigWindow, showConfigWindow } from "./windows/configWindow";
import { createOverlayWindow } from "./windows/overlayWindow";
import { createButtonsWindow, resetButtonsPosition } from "./windows/buttonsWindow";
import { createTrackingWindow } from "./windows/trackingWindow";

function readSavedButtonsPosition(): { x: number | null; y: number | null } {
  try {
    const raw = JSON.parse(fs.readFileSync("config.json", "utf-8"));
    return { x: raw.action_buttons?.x ?? null, y: raw.action_buttons?.y ?? null };
  } catch {
    return { x: null, y: null };
  }
}

Menu.setApplicationMenu(null);

export let backend: BackendServer;
let engine: TrackingEngine;
let quitting = false;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    showConfigWindow();
  });

  app.whenReady().then(() => {
    const config = loadConfig("config.json");
    applyCursor(config.cursor.size_px, config.cursor.mode, config.cursor.custom_color);
    const { width, height } = screen.getPrimaryDisplay().size;

    engine = new TrackingEngine(config, new NutJsMouseDriver(), [width, height], (gesture, action, position) => {
      clickLog.record(gesture, action, position);
      backend.emit("message", { type: "action", gesture, action, x: position[0], y: position[1] });
    });
    backend = new BackendServer({
      engine,
      config,
      configPath: "config.json",
      toggleTouchKeyboard,
      toggleVoiceTyping,
    });

    if (config.calibration.click_logging_enabled) clickLog.enable();

    backend.on("message", (message: { type: string; message?: string }) => {
      if (message.type !== "error") return;
      dialog.showErrorBox(
        "FaceMesh Mouse",
        "Não foi possível acessar a webcam. Verifique se ela está conectada e se " +
          "a permissão de câmera do Windows está ativa."
      );
      restoreCursor();
      app.quit();
    });

    backend.start();
    wireIpc(backend);
    createConfigWindow(backend);
    createOverlayWindow();
    const saved = readSavedButtonsPosition();
    createButtonsWindow(backend, saved.x, saved.y);
    createTray(backend);
    createTrackingWindow(backend);

    if (fs.existsSync("config.json")) {
      backend.send({ type: "start" });
    } else {
      showConfigWindow();
    }
  });
}

export { showConfigWindow, resetButtonsPosition };

app.on("before-quit", () => {
  quitting = true;
  backend?.send({ type: "stop" });
  backend?.stop();
  // Fire-and-forget: releases any held mouse-button drag so quitting
  // mid-drag doesn't leave the physical button held down system-wide.
  // Mirrors Python's Engine.stop() call in main()'s finally block. Not
  // awaited -- quitting must not block indefinitely on this.
  void engine?.stop();
  restoreCursor();
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  // Intentionally does not quit -- the app lives in the tray.
});
