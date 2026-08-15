import { app, dialog } from "electron";
import { BackendProcess } from "./backendProcess";
import { resolveBackendCommand } from "./backendCommand";

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

export let backend: BackendProcess;
let quitting = false;

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
});

app.on("before-quit", () => {
  quitting = true;
  backend?.send({ type: "stop" });
  backend?.stop();
});

app.on("window-all-closed", () => {
  // Intentionally does not quit -- the app lives in the tray with no
  // window open most of the time, same as today's Tkinter app.
});
