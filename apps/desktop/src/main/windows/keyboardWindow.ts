import { BrowserWindow, screen } from "electron";
import path from "node:path";
import type { BackendServer } from "../services/backendServer";
import { defaultPosition, resolvePosition, WIDTH, WINDOW_HEIGHT } from "./keyboardPosition";

let win: BrowserWindow | null = null;
let backendRef: BackendServer | null = null;

export function createKeyboardWindow(
  backend: BackendServer,
  savedX: number | null,
  savedY: number | null
): BrowserWindow {
  backendRef = backend;
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().bounds;
  const taskbarReservedPx = screenH - screen.getPrimaryDisplay().workArea.height;
  const { x, y } = resolvePosition(savedX, savedY, screenW, screenH, taskbarReservedPx);

  win = new BrowserWindow({
    x: Math.round(x),
    y: Math.round(y),
    width: WIDTH,
    height: WINDOW_HEIGHT,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    // Starts hidden -- shown only when the ⌨ button sends open_keyboard.
    // Never destroyed, so shift state / compact-vs-full mode in the
    // renderer's JS survives across opens for the rest of the process's life.
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "keyboard", "index.html"));

  return win;
}

export function showKeyboardWindow(): void {
  win?.showInactive();
}

export function hideKeyboardWindow(): void {
  win?.hide();
}

export function moveKeyboardWindow(dx: number, dy: number): void {
  if (!win) return;
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return;
  const [curX, curY] = win.getPosition();
  win.setPosition(curX + dx, curY + dy);
}

export function endKeyboardDrag(): void {
  if (!win || !backendRef) return;
  const [curX, curY] = win.getPosition();
  backendRef.send({
    type: "save_config",
    config: { custom_keyboard: { x: curX, y: curY } },
  });
}

export function resetKeyboardPosition(): void {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().bounds;
  const taskbarReservedPx = screenH - screen.getPrimaryDisplay().workArea.height;
  const { x, y } = defaultPosition(screenW, screenH, taskbarReservedPx);
  win?.setPosition(Math.round(x), Math.round(y));
}
