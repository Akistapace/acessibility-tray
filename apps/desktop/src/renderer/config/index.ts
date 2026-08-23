import { computeToggleState } from "./toggleState.js";
import { GESTURE_LABELS, GESTURE_NAMES, ACTION_LABELS } from "./labels.js";

interface AppConfigJson {
  calibration: Record<string, number | boolean>;
  gestures: Record<string, { action: string; threshold: number; cooldown_ms: number; hold_ms: number }>;
  action_buttons: { x: number | null; y: number | null };
  cursor: { size_px: number; mode: string; custom_color: string };
}

let currentConfig: AppConfigJson = {
  calibration: {
    sensitivity_x: 0.025,
    sensitivity_y: 0.05,
    acceleration: 0.5,
    motion_threshold_px: 0,
    yield_resume_after_s: 3,
    click_logging_enabled: true,
    dwell_click_enabled: false,
    dwell_time_s: 1,
    keyboard_button_enabled: true,
    voice_button_enabled: true,
  },
  gestures: {},
  action_buttons: { x: null, y: null },
  cursor: { size_px: 32, mode: "default", custom_color: "#000000" },
};

let lastStatus = { control_enabled: false, paused: false, no_face: false, yielded: false };

// The backend broadcasts a "config" message to EVERY window on every
// save_config (added so an already-open buttons window learns about a live
// keyboard/voice-toggle change) -- including one triggered by a totally
// unrelated window, e.g. the floating buttons window persisting a drag
// position. This window's own config form must only be repainted by a
// "config" message that is a direct response to a get_config/save_config
// request THIS window itself sent -- otherwise an unrelated save can wipe
// out in-progress, unsaved edits (including a live-applied-but-unsaved
// cursor theme) and desync the Extras tab from the actually-live cursor.
let awaitingConfigResponse = false;

const preview = document.getElementById("preview") as HTMLImageElement;
const statusLabel = document.getElementById("status-label") as HTMLDivElement;
const toggleButton = document.getElementById("toggle-button") as HTMLButtonElement;

function renderGestureRows(): void {
  const container = document.getElementById("gesture-rows") as HTMLDivElement;
  container.innerHTML = "";
  for (const name of GESTURE_NAMES) {
    const gesture = currentConfig.gestures[name];
    if (!gesture) continue;
    const row = document.createElement("div");
    row.className = "gesture-row";
    row.innerHTML = `
      <strong>${GESTURE_LABELS[name]}</strong>
      <progress id="bar-${name}" max="1" value="0"></progress>
      <select id="action-${name}">
        ${Object.entries(ACTION_LABELS)
          .map(([value, label]) => `<option value="${value}">${label}</option>`)
          .join("")}
      </select>
      <label>Espera (ms) <input type="range" id="hold-${name}" min="0" max="1000" step="10" /></label>
      <label>Intervalo (ms) <input type="range" id="cooldown-${name}" min="50" max="1500" step="10" /></label>
    `;
    container.appendChild(row);
    row.addEventListener("pointerenter", () => {
      window.backend.send({ type: "highlight_gesture", gesture: name });
    });
    row.addEventListener("pointerleave", () => {
      window.backend.send({ type: "highlight_gesture", gesture: null });
    });
    (row.querySelector(`#action-${name}`) as HTMLSelectElement).value = gesture.action;
    (row.querySelector(`#hold-${name}`) as HTMLInputElement).value = String(gesture.hold_ms);
    (row.querySelector(`#cooldown-${name}`) as HTMLInputElement).value = String(gesture.cooldown_ms);
  }
}

function applyConfigToForm(): void {
  for (const [id, value] of Object.entries(currentConfig.calibration)) {
    const el = document.getElementById(id) as HTMLInputElement | null;
    if (!el) continue;
    if (el.type === "checkbox") el.checked = Boolean(value);
    else el.value = String(value);
  }
  const cursorSizeEl = document.getElementById("cursor_size_px") as HTMLInputElement | null;
  if (cursorSizeEl) cursorSizeEl.value = String(currentConfig.cursor.size_px);
  const cursorModeEl = document.getElementById("cursor_mode") as HTMLSelectElement | null;
  if (cursorModeEl) cursorModeEl.value = currentConfig.cursor.mode;
  const cursorColorEl = document.getElementById("cursor_custom_color") as HTMLInputElement | null;
  if (cursorColorEl) cursorColorEl.value = currentConfig.cursor.custom_color;
  renderGestureRows();
}

function readFormIntoConfig(): void {
  for (const key of Object.keys(currentConfig.calibration)) {
    const el = document.getElementById(key) as HTMLInputElement | null;
    if (!el) continue;
    currentConfig.calibration[key] = el.type === "checkbox" ? el.checked : Number(el.value);
  }
  currentConfig.cursor = {
    size_px: Number((document.getElementById("cursor_size_px") as HTMLInputElement).value),
    mode: (document.getElementById("cursor_mode") as HTMLSelectElement).value,
    custom_color: (document.getElementById("cursor_custom_color") as HTMLInputElement).value,
  };
  for (const name of GESTURE_NAMES) {
    const actionEl = document.getElementById(`action-${name}`) as HTMLSelectElement | null;
    const holdEl = document.getElementById(`hold-${name}`) as HTMLInputElement | null;
    if (!actionEl || !holdEl || !currentConfig.gestures[name]) continue;
    currentConfig.gestures[name].action = actionEl.value;
    currentConfig.gestures[name].hold_ms = Number(holdEl.value);
    const cooldownEl = document.getElementById(`cooldown-${name}`) as HTMLInputElement | null;
    if (cooldownEl && currentConfig.gestures[name]) {
      currentConfig.gestures[name].cooldown_ms = Number(cooldownEl.value);
    }
  }
  currentConfig.cursor = {
    size_px: Number((document.getElementById("cursor_size_px") as HTMLInputElement).value),
    mode: (document.getElementById("cursor_mode") as HTMLSelectElement).value,
    custom_color: (document.getElementById("cursor_custom_color") as HTMLInputElement).value,
  };
}

// This window never owns action_buttons or custom_keyboard: the floating
// buttons window and the keyboard overlay window each persist their own
// position (and, for the keyboard, compact/full mode) straight to disk on
// every drag/toggle. currentConfig still holds whatever was on disk at
// page load, so sending either back would silently revert any change made
// since. Leaving both keys out entirely lets the backend's save_config
// merge keep the on-disk values.
function configPayloadWithoutButtons(): Record<string, unknown> {
  const { action_buttons: _ignored, custom_keyboard: _ignoredKeyboard, ...rest } = currentConfig as unknown as Record<string, unknown>;
  return rest;
}

function updateToggleButton(): void {
  const state = computeToggleState(lastStatus);
  statusLabel.textContent = state.statusText;
  statusLabel.dataset.state = !lastStatus.control_enabled
    ? "stopped"
    : lastStatus.paused
      ? "paused"
      : "running";
  toggleButton.textContent = state.buttonText;
  toggleButton.dataset.state = state.nextCommand;
}

toggleButton.addEventListener("click", () => {
  readFormIntoConfig();
  const state = computeToggleState(lastStatus);
  window.backend.send({ type: "update_config", config: configPayloadWithoutButtons() });
  window.backend.send({ type: state.nextCommand });
  if (state.nextCommand === "start" || state.nextCommand === "resume") {
    window.close();
  }
});

type SaveState = "idle" | "saving" | "saved";

const SAVE_CONFIRMATION_MS = 1400;
// Safety net: if the backend never echoes the config back (not running,
// or the message got lost), the button must not stay stuck on "Salvando…"
// forever.
const SAVE_TIMEOUT_MS = 4000;

let saveState: SaveState = "idle";
let saveConfirmTimer: ReturnType<typeof setTimeout> | null = null;
let saveTimeoutTimer: ReturnType<typeof setTimeout> | null = null;

function saveButtonLabel(state: SaveState): string {
  if (state === "saving") return "Salvando…";
  if (state === "saved") return "Salvo";
  return "Salvar configurações";
}

// All save-trigger buttons (one per tab) always mirror one shared state --
// a save started from any tab is one save of the whole config.
function setSaveState(state: SaveState): void {
  saveState = state;
  document.querySelectorAll<HTMLButtonElement>(".save-trigger").forEach((button) => {
    button.dataset.state = state;
    button.disabled = state === "saving";
    button.textContent = saveButtonLabel(state);
  });
}

function saveConfig(): void {
  readFormIntoConfig();
  awaitingConfigResponse = true;
  window.backend.send({ type: "save_config", config: configPayloadWithoutButtons() });
  if (saveConfirmTimer) clearTimeout(saveConfirmTimer);
  if (saveTimeoutTimer) clearTimeout(saveTimeoutTimer);
  setSaveState("saving");
  saveTimeoutTimer = setTimeout(() => setSaveState("idle"), SAVE_TIMEOUT_MS);
}

document.querySelectorAll(".save-trigger").forEach((button) => {
  button.addEventListener("click", saveConfig);
});

document.getElementById("reset-position-button")?.addEventListener("click", () => {
  window.backend.send({ type: "config:reset-position" });
});

// Debounced so dragging the size slider or picking a color doesn't flood
// the backend with set_cursor_theme commands (each one regenerates and
// re-applies the real Windows cursor, which would flicker if sent on every
// "input" event of a drag).
let cursorApplyTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleCursorApply(): void {
  if (cursorApplyTimer) clearTimeout(cursorApplyTimer);
  cursorApplyTimer = setTimeout(() => {
    readFormIntoConfig();
    window.backend.send({ type: "set_cursor_theme", ...currentConfig.cursor });
  }, 150);
}
for (const id of ["cursor_size_px", "cursor_mode", "cursor_custom_color"]) {
  document.getElementById(id)?.addEventListener("input", scheduleCursorApply);
}

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    button.classList.add("active");
    const tab = (button as HTMLElement).dataset.tab;
    document.getElementById(`tab-${tab}`)?.classList.add("active");
    // Navigating away from the Gestos tab must clear any in-progress hover
    // highlight -- pointerleave alone can't be relied on here (e.g. the
    // pointer may land on the tab button itself without ever leaving the
    // hovered row via a mouse-move event), so clear unconditionally.
    if (tab !== "gestos") {
      window.backend.send({ type: "highlight_gesture", gesture: null });
    }
  });
});

window.backend.on("status", (message) => {
  lastStatus = message as typeof lastStatus;
  updateToggleButton();
});

window.backend.on("frame", (message) => {
  const frame = message as { jpeg_b64: string; gesture_progress: Record<string, number> };
  preview.src = `data:image/jpeg;base64,${frame.jpeg_b64}`;
  for (const [name, value] of Object.entries(frame.gesture_progress)) {
    const bar = document.getElementById(`bar-${name}`) as HTMLProgressElement | null;
    if (bar) bar.value = value;
  }
});

window.backend.on("config", (message) => {
  // Ignore any "config" broadcast this window didn't itself ask for -- see
  // the awaitingConfigResponse comment above.
  if (!awaitingConfigResponse) return;
  awaitingConfigResponse = false;
  currentConfig = (message as { config: AppConfigJson }).config;
  applyConfigToForm();
  if (saveState === "saving") {
    if (saveTimeoutTimer) clearTimeout(saveTimeoutTimer);
    setSaveState("saved");
    saveConfirmTimer = setTimeout(() => setSaveState("idle"), SAVE_CONFIRMATION_MS);
  }
});

applyConfigToForm();
updateToggleButton();
awaitingConfigResponse = true;
window.backend.send({ type: "get_config" });
