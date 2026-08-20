import { app, dialog, globalShortcut, Menu, screen } from "electron";
import fs from "node:fs";
import { BackendServer } from "./services/backendServer";
import { TrackingEngine } from "./services/trackingEngine.service";
import { NutJsMouseDriver } from "./services/mouseController.service";
import { loadConfig } from "./services/config.service";
import { toggleTouchKeyboard } from "./services/win32.service";
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
    const { width, height } = screen.getPrimaryDisplay().size;

    const engine = new TrackingEngine(config, new NutJsMouseDriver(), [width, height], (gesture, action, position) => {
      // wired to clickLog.record + an `action` message in Task 17
    });
    backend = new BackendServer({
      engine,
      config,
      configPath: "config.json",
      toggleTouchKeyboard,
    });

    backend.on("message", (message: { type: string; message?: string }) => {
      if (message.type !== "error") return;
      dialog.showErrorBox(
        "FaceMesh Mouse",
        "Não foi possível acessar a webcam. Verifique se ela está conectada e se " +
          "a permissão de câmera do Windows está ativa."
      );
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
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  // Intentionally does not quit -- the app lives in the tray.
});
