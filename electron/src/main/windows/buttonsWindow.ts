import { BrowserWindow, ipcMain, screen } from "electron";
import path from "node:path";
import { BackendProcess } from "../backendProcess";
import { defaultPosition, resolvePosition, WIDTH, SIZE } from "./buttonsPosition";

let win: BrowserWindow | null = null;

export function createButtonsWindow(
  backend: BackendProcess,
  savedX: number | null,
  savedY: number | null
): BrowserWindow {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workArea;
  const taskbarReservedPx = screen.getPrimaryDisplay().bounds.height - screenH;
  const { x, y } = resolvePosition(savedX, savedY, screenW, screenH, taskbarReservedPx);

  win = new BrowserWindow({
    x: Math.round(x),
    y: Math.round(y),
    width: WIDTH,
    height: SIZE,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "buttons", "index.html"));
  win.showInactive();

  // These two channels are re-emitted by ipcRelay.ts (Step 7 below) rather
  // than delivered on the shared "backend:send" channel directly -- a raw
  // listener there would also see every command meant for Python (start,
  // update_config, ...) and would need to filter them back out itself.
  ipcMain.on("buttons:drag-move", (_event, message: { dx: number; dy: number }) => {
    if (!win) return;
    const [curX, curY] = win.getPosition();
    win.setPosition(curX + message.dx, curY + message.dy);
  });
  ipcMain.on("buttons:drag-end", () => {
    if (!win) return;
    const [curX, curY] = win.getPosition();
    backend.send({
      type: "save_config",
      config: { action_buttons: { x: curX, y: curY } },
    });
  });

  return win;
}

export function resetButtonsPosition(): void {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workArea;
  const taskbarReservedPx = screen.getPrimaryDisplay().bounds.height - screenH;
  const { x, y } = defaultPosition(screenW, screenH, taskbarReservedPx);
  win?.setPosition(Math.round(x), Math.round(y));
}
