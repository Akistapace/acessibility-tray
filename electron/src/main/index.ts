import { app, dialog, globalShortcut, Menu } from "electron";
import fs from "node:fs";
import { BackendProcess } from "./backendProcess";
import { resolveBackendCommand } from "./backendCommand";
import { wireBackendRelay } from "./ipcRelay";
import { createTray } from "./tray";
import { createConfigWindow, showConfigWindow } from "./windows/configWindow";
import { createOverlayWindow } from "./windows/overlayWindow";
import { createButtonsWindow, resetButtonsPosition } from "./windows/buttonsWindow";

function readSavedButtonsPosition(): { x: number | null; y: number | null } {
  try {
    const raw = JSON.parse(fs.readFileSync("config.json", "utf-8"));
    return { x: raw.action_buttons?.x ?? null, y: raw.action_buttons?.y ?? null };
  } catch {
    return { x: null, y: null };
  }
}

// This app has no menu-driven functionality (no File/Edit/View/Window/Help
// actions) -- the default menu Electron attaches to every BrowserWindow is
// pure clutter here, and worse, its Alt-key mnemonics compete with this
// app's own global shortcuts.
Menu.setApplicationMenu(null);

export let backend: BackendProcess;
let quitting = false;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  // app.quit() is async, so everything below has to sit in the else
  // branch -- otherwise the losing instance would still spawn its own
  // backend and windows before the quit lands.
  app.quit();
} else {
  // Relaunching while a copy is already running reopens the config
  // window instead of starting a second app, replacing the old
  // single_instance.py behaviour.
  app.on("second-instance", () => {
    showConfigWindow();
  });

  app.whenReady().then(() => {
    const { command, args } = resolveBackendCommand(app.isPackaged, process.resourcesPath);
    backend = new BackendProcess(command, args);

    backend.on("message", (message: { type: string; message?: string }) => {
      if (message.type !== "error") return;
      // Today's only real error case: the camera failed to open. The
      // backend sends this once, at startup, then returns without ever
      // starting its push loops -- there is nothing left running to
      // recover, so this is fatal.
      dialog.showErrorBox(
        "FaceMesh Mouse",
        "Não foi possível acessar a webcam. Verifique se ela está conectada e se " +
          "a permissão de câmera do Windows está ativa."
      );
      app.quit();
    });

    backend.on("exit", (code) => {
      if (quitting || code === 0) return;
      // The backend died mid-session (not from our own before-quit) --
      // this failure mode doesn't exist in the old Tkinter app, where
      // engine and UI shared one process and a crash took both down
      // together silently. Here the window would otherwise sit frozen
      // with a dead backend behind it, so ask instead.
      const choice = dialog.showMessageBoxSync({
        type: "error",
        message: "FaceMesh Mouse",
        detail: `O processo de rastreamento parou inesperadamente (código ${code}).`,
        buttons: ["Reiniciar", "Sair"],
        defaultId: 0,
      });
      if (choice === 0) {
        backend.start();
      } else {
        app.quit();
      }
    });

    backend.on("log", (text: string) => console.error(`[backend] ${text}`));
    backend.start();
    wireBackendRelay(backend);
    createConfigWindow(backend);
    createOverlayWindow();
    const saved = readSavedButtonsPosition();
    createButtonsWindow(backend, saved.x, saved.y);
    createTray(backend);

    // Same launch behaviour as the old Tkinter main.py: a first run (no
    // config.json yet) opens the config window and stays stopped, while
    // every later run starts control right away with no window shown.
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
  // Intentionally does not quit -- the app lives in the tray with no
  // window open most of the time, same as today's Tkinter app.
});
