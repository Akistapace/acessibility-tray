import { BrowserWindow, screen } from "electron";
import path from "node:path";
import type { BackendServer } from "../services/backendServer";
import { defaultPosition, resolvePosition, WIDTH, SIZE } from "./buttonsPosition";

let win: BrowserWindow | null = null;
let backendRef: BackendServer | null = null;

export function createButtonsWindow(
  backend: BackendServer,
  savedX: number | null,
  savedY: number | null
): BrowserWindow {
  backendRef = backend;
  // bounds, not workArea: defaultPosition/resolvePosition subtract the
  // taskbar themselves, so feeding them the already-shrunk workArea height
  // would place the buttons one taskbar-height too high.
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().bounds;
  const taskbarReservedPx = screenH - screen.getPrimaryDisplay().workArea.height;
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

  return win;
}

// Was an inline ipcMain.on("buttons:drag-move", ...) listener in this file;
// now called from ipc/buttons.ipc.ts so window ownership (this file) and
// IPC routing (ipc/) stay separate, per the main/{windows,ipc} split.
export function moveButtonsWindow(dx: number, dy: number): void {
  if (!win) return;
  const [curX, curY] = win.getPosition();
  win.setPosition(curX + dx, curY + dy);
}

// Was an inline ipcMain.on("buttons:drag-end", ...) listener; now called
// from ipc/buttons.ipc.ts.
export function endButtonsDrag(): void {
  if (!win || !backendRef) return;
  const [curX, curY] = win.getPosition();
  backendRef.send({
    type: "save_config",
    config: { action_buttons: { x: curX, y: curY } },
  });
}

export function resetButtonsPosition(): void {
  // bounds, not workArea: see createButtonsWindow above.
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().bounds;
  const taskbarReservedPx = screenH - screen.getPrimaryDisplay().workArea.height;
  const { x, y } = defaultPosition(screenW, screenH, taskbarReservedPx);
  win?.setPosition(Math.round(x), Math.round(y));
}
