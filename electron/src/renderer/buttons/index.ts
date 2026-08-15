import { isClick } from "./clickOrDrag.js";

declare global {
  interface Window {
    backend: {
      send: (message: Record<string, unknown>) => void;
      on: (channel: string, callback: (message: unknown) => void) => () => void;
    };
  }
}

let press: { x: number; y: number } | null = null;

function onPointerDown(event: PointerEvent, target: "keyboard" | "mic"): void {
  press = { x: event.screenX, y: event.screenY };
  (event.target as HTMLElement).setPointerCapture(event.pointerId);
  (event.target as HTMLElement).dataset.target = target;
}

function onPointerUp(event: PointerEvent): void {
  if (!press) return;
  const release = { x: event.screenX, y: event.screenY };
  const target = (event.target as HTMLElement).dataset.target;
  if (isClick(press, release)) {
    if (target === "keyboard") {
      window.backend.send({ type: "open_keyboard", x: release.x, y: release.y });
    } else if (target === "mic") {
      window.backend.send({ type: "open_voice_typing" });
    }
  } else {
    // Dragging moved the whole OS window already (see onPointerMove);
    // tell the main process the drag ended so it can persist the spot.
    window.backend.send({ type: "buttons:drag-end" });
  }
  press = null;
}

function onPointerMove(event: PointerEvent): void {
  if (!press || event.buttons !== 1) return;
  const dx = event.screenX - press.x;
  const dy = event.screenY - press.y;
  if (Math.abs(dx) > 0 || Math.abs(dy) > 0) {
    ipcMoveWindow(dx, dy);
  }
}

function ipcMoveWindow(dx: number, dy: number): void {
  window.backend.send({ type: "buttons:drag-move", dx, dy });
}

const keyboard = document.getElementById("keyboard") as HTMLDivElement;
const mic = document.getElementById("mic") as HTMLDivElement;
for (const [el, name] of [
  [keyboard, "keyboard"],
  [mic, "mic"],
] as const) {
  el.addEventListener("pointerdown", (e) => onPointerDown(e, name));
  el.addEventListener("pointerup", onPointerUp);
  el.addEventListener("pointermove", onPointerMove);
}
