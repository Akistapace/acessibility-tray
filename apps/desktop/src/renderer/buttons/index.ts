import { isKeyboardButtonEnabled, isVoiceButtonEnabled } from "./buttonVisibility.js";
import { isClick } from "./clickOrDrag.js";

// Updated after every pointermove so ipcMoveWindow always gets the delta
// since the PREVIOUS move event, not the cumulative distance from
// drag-start -- buttonsWindow.ts adds each received delta onto the
// window's current (already-moved) position, so sending a cumulative
// distance-from-start on every event would compound and make the window
// accelerate away from the cursor.
let lastMovePos: { x: number; y: number } | null = null;

function onHandlePointerDown(event: PointerEvent): void {
  lastMovePos = { x: event.screenX, y: event.screenY };
  (event.target as HTMLElement).setPointerCapture(event.pointerId);
}

function onHandlePointerMove(event: PointerEvent): void {
  if (!lastMovePos || event.buttons !== 1) return;
  const dx = event.screenX - lastMovePos.x;
  const dy = event.screenY - lastMovePos.y;
  if (dx !== 0 || dy !== 0) {
    window.backend.send({ type: "buttons:drag-move", dx, dy });
    lastMovePos = { x: event.screenX, y: event.screenY };
  }
}

function onHandlePointerUp(): void {
  if (!lastMovePos) return;
  lastMovePos = null;
  // The window already moved live (see onHandlePointerMove); tell the
  // main process the drag ended so it can persist the spot.
  window.backend.send({ type: "buttons:drag-end" });
}

const dragHandle = document.getElementById("drag-handle") as HTMLDivElement;
dragHandle.addEventListener("pointerdown", onHandlePointerDown);
dragHandle.addEventListener("pointermove", onHandlePointerMove);
dragHandle.addEventListener("pointerup", onHandlePointerUp);

const keyboard = document.getElementById("keyboard") as HTMLDivElement;
const mic = document.getElementById("mic") as HTMLDivElement;

// The circles are draggable too (not just the top grip handle) -- press,
// move past CLICK_DRAG_THRESHOLD_PX, and it's a drag; release within the
// threshold and it's a click that opens the keyboard/mic. Matches the
// press/lastMovePos split used by the drag-handle above: lastMovePos feeds
// per-event deltas to buttons:drag-move, while `press` keeps the original
// down position for the isClick(press, release) check at pointerup.
let circlePress: { x: number; y: number } | null = null;
let circleLastMovePos: { x: number; y: number } | null = null;

function onCirclePointerDown(event: PointerEvent, target: "keyboard" | "mic"): void {
  circlePress = { x: event.screenX, y: event.screenY };
  circleLastMovePos = circlePress;
  const el = event.target as HTMLElement;
  el.setPointerCapture(event.pointerId);
  el.dataset.target = target;
}

function onCirclePointerMove(event: PointerEvent): void {
  if (!circleLastMovePos || event.buttons !== 1) return;
  const dx = event.screenX - circleLastMovePos.x;
  const dy = event.screenY - circleLastMovePos.y;
  if (dx !== 0 || dy !== 0) {
    window.backend.send({ type: "buttons:drag-move", dx, dy });
    circleLastMovePos = { x: event.screenX, y: event.screenY };
  }
}

function onCirclePointerUp(event: PointerEvent): void {
  if (!circlePress) return;
  const release = { x: event.screenX, y: event.screenY };
  const target = (event.target as HTMLElement).dataset.target;
  if (isClick(circlePress, release)) {
    if (target === "keyboard") {
      window.backend.send({ type: "open_keyboard", x: release.x, y: release.y });
    } else if (target === "mic") {
      window.backend.send({ type: "open_voice_typing" });
    }
  } else {
    window.backend.send({ type: "buttons:drag-end" });
  }
  circlePress = null;
  circleLastMovePos = null;
}

for (const [el, name] of [
  [keyboard, "keyboard"],
  [mic, "mic"],
] as const) {
  el.addEventListener("pointerdown", (e) => onCirclePointerDown(e, name));
  el.addEventListener("pointermove", onCirclePointerMove);
  el.addEventListener("pointerup", onCirclePointerUp);
}

window.backend.on("config", (message) => {
  const { config } = message as { config: Parameters<typeof isKeyboardButtonEnabled>[0] };
  keyboard.style.display = isKeyboardButtonEnabled(config) ? "" : "none";
  mic.style.display = isVoiceButtonEnabled(config) ? "" : "none";
});

// This window never requests get_config on its own otherwise -- it only
// learns the current config when some other window happens to trigger a
// "config" broadcast. Ask for it explicitly on load so a keyboard/voice
// button hidden via the Extras tab stays hidden across a restart.
window.backend.send({ type: "get_config" });
