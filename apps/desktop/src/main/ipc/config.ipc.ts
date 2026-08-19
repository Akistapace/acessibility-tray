import { ipcMain } from "electron";
import { resetButtonsPosition } from "../windows/buttonsWindow";

export function registerConfigIpc(): void {
  ipcMain.on("config:reset-position", () => {
    resetButtonsPosition();
  });
}
