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
// Updated after every pointermove so ipcMoveWindow always gets the delta
// since the PREVIOUS move event, not the cumulative distance from
// drag-start -- buttonsWindow.ts adds each received delta onto the
// window's current (already-moved) position, so sending a cumulative
// distance-from-start on every event would compound and make the window
// accelerate away from the cursor. `press` itself stays untouched for the
// whole gesture -- onPointerUp's isClick(press, release) check needs the
// true original down position, not the last move position.
let lastMovePos: { x: number; y: number } | null = null;

function onPointerDown(event: PointerEvent, target: "keyboard" | "mic"): void {
  press = { x: event.screenX, y: event.screenY };
  lastMovePos = { x: event.screenX, y: event.screenY };
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
  lastMovePos = null;
}

function onPointerMove(event: PointerEvent): void {
  if (!lastMovePos || event.buttons !== 1) return;
  const dx = event.screenX - lastMovePos.x;
  const dy = event.screenY - lastMovePos.y;
  if (dx !== 0 || dy !== 0) {
    ipcMoveWindow(dx, dy);
    lastMovePos = { x: event.screenX, y: event.screenY };
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
