import { computeToggleState } from "./toggleState.js";
import { GESTURE_LABELS, GESTURE_NAMES, ACTION_LABELS } from "./labels.js";

declare global {
  interface Window {
    backend: {
      send: (message: Record<string, unknown>) => void;
      on: (channel: string, callback: (message: unknown) => void) => () => void;
    };
  }
}

interface AppConfigJson {
  calibration: Record<string, number | boolean>;
  gestures: Record<string, { action: string; threshold: number; cooldown_ms: number; hold_ms: number }>;
  action_buttons: { x: number | null; y: number | null };
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
  },
  gestures: {},
  action_buttons: { x: null, y: null },
};

let lastStatus = { control_enabled: false, paused: false, no_face: false, yielded: false };

const preview = document.getElementById("preview") as HTMLImageElement;
const statusLabel = document.getElementById("status-label") as HTMLDivElement;
const toggleButton = document.getElementById("toggle-button") as HTMLButtonElement;
const saveButton = document.getElementById("save-button") as HTMLButtonElement;

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
  renderGestureRows();
}

function readFormIntoConfig(): void {
  for (const key of Object.keys(currentConfig.calibration)) {
    const el = document.getElementById(key) as HTMLInputElement | null;
    if (!el) continue;
    currentConfig.calibration[key] = el.type === "checkbox" ? el.checked : Number(el.value);
  }
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
}

// This window never owns action_buttons: the floating buttons window
// persists its own position on every drag, straight to disk. currentConfig
// still holds whatever was on disk at page load, so sending it back would
// silently revert any drag made since. Leaving the key out entirely lets
// the backend's save_config merge keep the on-disk position.
function configPayloadWithoutButtons(): Record<string, unknown> {
  const { action_buttons: _ignored, ...rest } = currentConfig;
  return rest;
}

function updateToggleButton(): void {
  const state = computeToggleState(lastStatus);
  statusLabel.textContent = state.statusText;
  toggleButton.textContent = state.buttonText;
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

saveButton.addEventListener("click", () => {
  readFormIntoConfig();
  window.backend.send({ type: "save_config", config: configPayloadWithoutButtons() });
});

document.getElementById("reset-position-button")?.addEventListener("click", () => {
  window.backend.send({ type: "config:reset-position" });
});

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(`tab-${(button as HTMLElement).dataset.tab}`)?.classList.add("active");
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
  currentConfig = (message as { config: AppConfigJson }).config;
  applyConfigToForm();
});

applyConfigToForm();
updateToggleButton();
window.backend.send({ type: "get_config" });
