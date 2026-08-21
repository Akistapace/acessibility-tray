import { isKeyboardButtonEnabled, isVoiceButtonEnabled } from "./buttonVisibility.js";

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

keyboard.addEventListener("click", (event) => {
  window.backend.send({ type: "open_keyboard", x: event.screenX, y: event.screenY });
});
mic.addEventListener("click", () => {
  window.backend.send({ type: "open_voice_typing" });
});

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
