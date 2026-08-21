import { ipcMain } from "electron";
import type { BackendServer } from "../services/backendServer";
import type { TrackingFrame } from "@facemesh-mouse/shared";

export function registerTrackingIpc(backend: BackendServer): void {
  ipcMain.on("tracking:frame", (_event, frame: TrackingFrame) => {
    void backend.onTrackingFrame(frame);
  });
  ipcMain.on("tracking:camera-error", () => {
    backend.emit("message", { type: "error", message: "camera" });
  });
}
