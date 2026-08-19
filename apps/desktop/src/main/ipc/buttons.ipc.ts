import { ipcMain } from "electron";
import { moveButtonsWindow, endButtonsDrag } from "../windows/buttonsWindow";

// These two channels are re-emitted by ipc/relay.ts's wireBackendRelay
// rather than delivered on the shared "backend:send" channel directly -- a
// raw listener there would also see every command meant for Python (start,
// update_config, ...) and would need to filter them back out itself.
export function registerButtonsIpc(): void {
  ipcMain.on("buttons:drag-move", (_event, message: { dx: number; dy: number }) => {
    moveButtonsWindow(message.dx, message.dy);
  });
  ipcMain.on("buttons:drag-end", () => {
    endButtonsDrag();
  });
}
