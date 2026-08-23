import { LETTER_ROWS, ACCENT_ROW, FULL_EXTRA_ROWS, keyOutput } from "./layout.js";

let shiftActive = false;
let compact = true;

const keysContainer = document.getElementById("keys") as HTMLDivElement;
const modeToggle = document.getElementById("mode-toggle") as HTMLButtonElement;
const closeButton = document.getElementById("close-button") as HTMLButtonElement;
const dragHandle = document.getElementById("drag-handle") as HTMLDivElement;

function makeKey(label: string, onClick: () => void, extraClass?: string): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.className = extraClass ? `key ${extraClass}` : "key";
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function makeRow(chars: readonly string[]): HTMLDivElement {
  const row = document.createElement("div");
  row.className = "row";
  for (const char of chars) {
    row.appendChild(
      makeKey(char, () => {
        window.backend.send({ type: "keyboard:type", text: keyOutput(char, shiftActive) });
      })
    );
  }
  return row;
}

function render(): void {
  keysContainer.innerHTML = "";
  if (!compact) {
    for (const row of FULL_EXTRA_ROWS) keysContainer.appendChild(makeRow(row));
  }
  for (const row of LETTER_ROWS) keysContainer.appendChild(makeRow(row));
  keysContainer.appendChild(makeRow(ACCENT_ROW));

  const bottomRow = document.createElement("div");
  bottomRow.className = "row";
  const shiftKey = makeKey(
    "⇧",
    () => {
      shiftActive = !shiftActive;
      shiftKey.classList.toggle("active", shiftActive);
    },
    "shift-key"
  );
  const spaceKey = makeKey(
    " ",
    () => window.backend.send({ type: "keyboard:type", text: " " }),
    "space-key"
  );
  const backspaceKey = makeKey("⌫", () => window.backend.send({ type: "keyboard:backspace" }));
  const enterKey = makeKey("⏎", () => window.backend.send({ type: "keyboard:enter" }));
  bottomRow.append(shiftKey, spaceKey, backspaceKey, enterKey);
  keysContainer.appendChild(bottomRow);
}

modeToggle.addEventListener("click", () => {
  compact = !compact;
  render();
  window.backend.send({ type: "save_config", config: { custom_keyboard: { compact } } });
});

closeButton.addEventListener("click", () => {
  window.backend.send({ type: "keyboard:close" });
});

// Same press/move/threshold-free drag pattern as buttons/index.ts's
// drag-handle -- the whole strip is the drag target, individual keys never
// double as one.
let lastMovePos: { x: number; y: number } | null = null;

dragHandle.addEventListener("pointerdown", (event) => {
  lastMovePos = { x: event.screenX, y: event.screenY };
  (event.target as HTMLElement).setPointerCapture(event.pointerId);
});

dragHandle.addEventListener("pointermove", (event) => {
  if (!lastMovePos || event.buttons !== 1) return;
  const dx = event.screenX - lastMovePos.x;
  const dy = event.screenY - lastMovePos.y;
  if (dx !== 0 || dy !== 0) {
    window.backend.send({ type: "keyboard:drag-move", dx, dy });
    lastMovePos = { x: event.screenX, y: event.screenY };
  }
});

dragHandle.addEventListener("pointerup", () => {
  if (!lastMovePos) return;
  lastMovePos = null;
  window.backend.send({ type: "keyboard:drag-end" });
});

window.backend.on("config", (message) => {
  const { config } = message as { config?: { custom_keyboard?: { compact?: boolean } } };
  compact = config?.custom_keyboard?.compact !== false;
  render();
});

window.backend.send({ type: "get_config" });
render();
