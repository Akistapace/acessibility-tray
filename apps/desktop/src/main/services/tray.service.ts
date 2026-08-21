import { app, globalShortcut, Menu, nativeImage, Tray } from "electron";
import path from "node:path";
import type { BackendServer } from "./backendServer";
import { computeTrayState, TrayStatus } from "./trayState";
import { showConfigWindow } from "../windows/configWindow";

const ICON_FILES: Record<string, string> = {
  running: "tray-running.png",
  paused: "tray-paused.png",
  no_face: "tray-no-face.png",
  yielded: "tray-yielded.png",
};

let tray: Tray | null = null;
let lastStatus: TrayStatus = { control_enabled: false, paused: false, no_face: false, yielded: false };

export function createTray(backend: BackendServer): Tray {
  const iconPath = path.join(__dirname, "..", "..", "assets", ICON_FILES.running);
  tray = new Tray(nativeImage.createFromPath(iconPath));
  tray.setToolTip("FaceMesh Mouse");

  function togglePause(): void {
    backend.send({ type: lastStatus.paused ? "resume" : "pause" });
  }

  const menu = Menu.buildFromTemplate([
    { label: "Pausar/Retomar", click: togglePause },
    { label: "Reabrir Config", click: showConfigWindow },
    { label: "Sair", click: () => app.quit() },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", showConfigWindow);

  backend.on("message", (message: { type: string }) => {
    if (message.type !== "status") return;
    lastStatus = message as unknown as TrayStatus;
    const state = computeTrayState(lastStatus);
    tray?.setImage(nativeImage.createFromPath(path.join(__dirname, "..", "..", "assets", ICON_FILES[state.icon])));
    tray?.setToolTip(state.title);
  });

  globalShortcut.register("Ctrl+Alt+P", togglePause);
  globalShortcut.register("Ctrl+Alt+O", showConfigWindow);

  return tray;
}
