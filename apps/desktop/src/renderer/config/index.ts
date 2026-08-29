import { computeToggleState } from "./toggleState.js";
import { GESTURE_LABELS, GESTURE_NAMES, ACTION_LABELS } from "./labels.js";

interface AppConfigJson {
  calibration: Record<string, number | boolean | string | null>;
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
    click_log_path: null,
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

// Preset buttons above the Movimento sliders are a pure UI convenience --
// the backend only ever sees the five underlying calibration numbers. Each
// preset's values are approximate, hand-picked translations of "gentle /
// default / fast" onto this app's actual slider ranges (CALIBRATION_RANGES
// in config.service.ts); "padrão" matches the shipped defaultCalibration()
// exactly so it's always a safe, reversible choice.
const PRESET_FIELDS = ["sensitivity_x", "sensitivity_y", "acceleration", "motion_threshold_px", "yield_resume_after_s"] as const;
type PresetField = (typeof PRESET_FIELDS)[number];
const PRESETS: Record<string, Record<PresetField, number>> = {
  suave: { sensitivity_x: 0.015, sensitivity_y: 0.015, acceleration: 0, motion_threshold_px: 4, yield_resume_after_s: 4 },
  padrao: { sensitivity_x: 0.025, sensitivity_y: 0.05, acceleration: 0.5, motion_threshold_px: 0, yield_resume_after_s: 3 },
  rapido: { sensitivity_x: 0.05, sensitivity_y: 0.07, acceleration: 0.8, motion_threshold_px: 0, yield_resume_after_s: 1.5 },
};

// A config saved before presets existed (or hand-tuned since) won't match
// any preset's exact numbers -- falling back to "personalizado" in that
// case keeps the real sliders visible instead of silently hiding a user's
// existing custom tuning behind a preset that doesn't actually match it.
function detectPreset(): string {
  for (const [id, vals] of Object.entries(PRESETS)) {
    const isMatch = PRESET_FIELDS.every((field) => Math.abs((currentConfig.calibration[field] as number) - vals[field]) < 1e-9);
    if (isMatch) return id;
  }
  return "personalizado";
}

function setPresetUI(id: string): void {
  document.querySelectorAll<HTMLElement>(".preset-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.preset === id);
  });
  const customCard = document.getElementById("custom-sliders");
  if (customCard) customCard.style.display = id === "personalizado" ? "flex" : "none";
}

document.querySelectorAll<HTMLElement>(".preset-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const id = btn.dataset.preset as string;
    if (id !== "personalizado") {
      const vals = PRESETS[id];
      for (const field of PRESET_FIELDS) {
        const el = document.getElementById(field) as HTMLInputElement | null;
        if (el) el.value = String(vals[field]);
        currentConfig.calibration[field] = vals[field];
      }
      initRangeOutputs();
    }
    setPresetUI(id);
  });
});

function updateDwellTimeVisibility(): void {
  const enabled = (document.getElementById("dwell_click_enabled") as HTMLInputElement | null)?.checked ?? false;
  const row = document.getElementById("dwell-time-row");
  if (row) row.style.display = enabled ? "" : "none";
}
document.getElementById("dwell_click_enabled")?.addEventListener("change", updateDwellTimeVisibility);

// Card expand/collapse is session-local UI state, not persisted -- reopening
// the window always starts every gesture collapsed, same as the config file
// never remembering which accordion panel was open.
const expandedGestures = new Set<string>();
// Remembers the last real (non-"none") action picked for a gesture so
// toggling it back on after toggling off restores what the user had,
// instead of always resetting to the first entry in ACTION_LABELS.
const lastGestureAction: Record<string, string> = {};
const FIRST_REAL_ACTION = Object.keys(ACTION_LABELS).find((key) => key !== "none") ?? "left_click";

function renderGestureRows(): void {
  const container = document.getElementById("gesture-rows") as HTMLDivElement;
  container.innerHTML = "";
  const actionOptionsHtml = Object.entries(ACTION_LABELS)
    .map(([value, label]) => `<option value="${value}">${label}</option>`)
    .join("");
  for (const name of GESTURE_NAMES) {
    const gesture = currentConfig.gestures[name];
    if (!gesture) continue;
    if (gesture.action !== "none") lastGestureAction[name] = gesture.action;

    const expanded = expandedGestures.has(name);
    const card = document.createElement("div");
    card.className = "gesture-card" + (expanded ? " expanded" : "");
    card.innerHTML = `
      <div class="gesture-header">
        <div class="gesture-name">${GESTURE_LABELS[name]}</div>
        <select id="action-${name}">${actionOptionsHtml}</select>
        <label class="switch">
          <input type="checkbox" id="enabled-${name}" />
          <span class="switch-track"><span class="switch-knob"></span></span>
        </label>
        <button type="button" class="gesture-expand" id="expand-${name}">${expanded ? "▲" : "▼"}</button>
      </div>
      <progress id="bar-${name}" class="gesture-progress" max="1" value="0"></progress>
      <div class="gesture-body">
        <label>
          <div class="range-row"><span>Sensibilidade de detecção</span><output for="sensitivity-${name}" class="range-value"></output></div>
          <input type="range" id="sensitivity-${name}" min="0" max="1" step="0.01" />
          <div class="range-desc">Quão forte o gesto precisa ser pra contar. Mais baixo = mais fácil de disparar (mas mais chance de disparar sem querer).</div>
        </label>
        <label>
          <div class="range-row"><span>Tempo para acionar (ms)</span><output for="hold-${name}" class="range-value"></output></div>
          <input type="range" id="hold-${name}" min="0" max="1000" step="10" />
          <div class="range-desc">Quanto tempo segurar o gesto até ele disparar a ação.</div>
        </label>
        <label>
          <div class="range-row"><span>Intervalo entre cliques (ms)</span><output for="cooldown-${name}" class="range-value"></output></div>
          <input type="range" id="cooldown-${name}" min="50" max="1500" step="10" />
          <div class="range-desc">Tempo mínimo de espera antes que o mesmo gesto possa disparar de novo.</div>
        </label>
      </div>
    `;
    container.appendChild(card);

    card.addEventListener("pointerenter", () => {
      window.backend.send({ type: "highlight_gesture", gesture: name });
    });
    card.addEventListener("pointerleave", () => {
      window.backend.send({ type: "highlight_gesture", gesture: null });
    });

    const actionEl = card.querySelector(`#action-${name}`) as HTMLSelectElement;
    const enabledEl = card.querySelector(`#enabled-${name}`) as HTMLInputElement;
    const expandEl = card.querySelector(`#expand-${name}`) as HTMLButtonElement;
    actionEl.value = gesture.action;
    enabledEl.checked = gesture.action !== "none";
    (card.querySelector(`#sensitivity-${name}`) as HTMLInputElement).value = String(gesture.threshold);
    (card.querySelector(`#hold-${name}`) as HTMLInputElement).value = String(gesture.hold_ms);
    (card.querySelector(`#cooldown-${name}`) as HTMLInputElement).value = String(gesture.cooldown_ms);

    // The action dropdown and the on/off switch both drive the same
    // underlying "action" field -- keep them mirrored so picking "(nenhuma)"
    // from the dropdown flips the switch off, and vice versa.
    actionEl.addEventListener("change", () => {
      if (actionEl.value !== "none") lastGestureAction[name] = actionEl.value;
      enabledEl.checked = actionEl.value !== "none";
    });
    enabledEl.addEventListener("change", () => {
      if (enabledEl.checked) {
        actionEl.value = lastGestureAction[name] ?? FIRST_REAL_ACTION;
      } else {
        if (actionEl.value !== "none") lastGestureAction[name] = actionEl.value;
        actionEl.value = "none";
      }
    });
    expandEl.addEventListener("click", () => {
      const isExpanded = card.classList.toggle("expanded");
      expandEl.textContent = isExpanded ? "▲" : "▼";
      if (isExpanded) expandedGestures.add(name);
      else expandedGestures.delete(name);
    });
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
  document.getElementById("cursor-mode-custom-polygon")?.setAttribute("fill", currentConfig.cursor.custom_color);
  updateCustomColorVisibility();
  updateCursorModeTiles();
  updateDwellTimeVisibility();
  setPresetUI(detectPreset());
  renderGestureRows();
  initRangeOutputs();
}

// The custom-color picker only means something when mode is "custom" --
// showing it for every mode (default/white/black/mista) implies it's live
// when it isn't.
function updateCustomColorVisibility(): void {
  const mode = (document.getElementById("cursor_mode") as HTMLSelectElement | null)?.value;
  const row = document.getElementById("cursor_custom_color_row") as HTMLElement | null;
  if (row) row.style.display = mode === "custom" ? "" : "none";
}
document.getElementById("cursor_mode")?.addEventListener("change", updateCustomColorVisibility);

// Visual pointer-style picker (mirrors Windows' own Settings > Mouse
// pointer "style" tiles) -- the real state of record stays the hidden
// #cursor_mode <select> above, so every existing read/save/apply path
// (readFormIntoConfig, scheduleCursorApply, the reset button) keeps
// working unchanged; a tile click just sets that select's value and
// dispatches "input" so scheduleCursorApply's existing listener fires.
function updateCursorModeTiles(): void {
  const mode = (document.getElementById("cursor_mode") as HTMLSelectElement | null)?.value;
  document.querySelectorAll<HTMLElement>(".cursor-mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
}

document.querySelectorAll<HTMLElement>(".cursor-mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const selectEl = document.getElementById("cursor_mode") as HTMLSelectElement;
    selectEl.value = btn.dataset.mode ?? "default";
    selectEl.dispatchEvent(new Event("input", { bubbles: true }));
    updateCustomColorVisibility();
    updateCursorModeTiles();
  });
});

// The "Personalizada" tile previews the actual chosen custom color live,
// same as Windows' own custom-color tile does.
document.getElementById("cursor_custom_color")?.addEventListener("input", () => {
  const colorEl = document.getElementById("cursor_custom_color") as HTMLInputElement;
  const polygon = document.getElementById("cursor-mode-custom-polygon");
  polygon?.setAttribute("fill", colorEl.value);
});

// Keeps each slider's <output for="..."> in sync with its current value --
// both right after a programmatic .value assignment (initial load, config
// broadcast) and live while the user drags, via the delegated "input"
// listener below.
function updateRangeOutput(el: HTMLInputElement): void {
  const output = el.parentElement?.querySelector<HTMLOutputElement>(`output[for="${el.id}"]`);
  if (output) output.textContent = el.value;
}

function initRangeOutputs(): void {
  document.querySelectorAll<HTMLInputElement>('input[type="range"]').forEach(updateRangeOutput);
}

document.addEventListener("input", (event) => {
  const target = event.target;
  if (target instanceof HTMLInputElement && target.type === "range") updateRangeOutput(target);
});

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
    const sensitivityEl = document.getElementById(`sensitivity-${name}`) as HTMLInputElement | null;
    if (sensitivityEl && currentConfig.gestures[name]) {
      currentConfig.gestures[name].threshold = Number(sensitivityEl.value);
    }
  }
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

// Mirrors defaultCursor() in config.service.ts.
document.getElementById("reset-cursor-button")?.addEventListener("click", () => {
  const sizeEl = document.getElementById("cursor_size_px") as HTMLInputElement;
  const modeEl = document.getElementById("cursor_mode") as HTMLSelectElement;
  const colorEl = document.getElementById("cursor_custom_color") as HTMLInputElement;
  sizeEl.value = "32";
  modeEl.value = "default";
  colorEl.value = "#000000";
  updateRangeOutput(sizeEl);
  document.getElementById("cursor-mode-custom-polygon")?.setAttribute("fill", "#000000");
  updateCustomColorVisibility();
  updateCursorModeTiles();
  scheduleCursorApply();
});

// The resolved path is owned by the backend (clickLog.service.ts's own
// default lives in the main process, not something this sandboxed renderer
// can compute), so display and currentConfig are both only ever updated
// from the "click_log_path" broadcast below -- never guessed locally.
function renderClickLogPath(logPath: string, isDefault: boolean): void {
  const display = document.getElementById("click-log-path-display");
  if (display) display.textContent = `Salvo em: ${logPath}`;
  // Keeping this in sync with what's actually live means a later "Salvar"
  // persists what the backend is really using right now. isDefault keeps
  // that as null (portable -- resolves correctly on whatever machine/user
  // profile actually runs the app) instead of baking in this one absolute
  // path the moment the user picks "Padrão".
  currentConfig.calibration.click_log_path = isDefault ? null : logPath;
}

document.getElementById("choose-click-log-path-button")?.addEventListener("click", () => {
  window.backend.send({ type: "choose_click_log_path" });
});
document.getElementById("reset-click-log-path-button")?.addEventListener("click", () => {
  window.backend.send({ type: "reset_click_log_path" });
});

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

// FAQ accordion in the Ajuda tab is static markup and purely local UI state
// (nothing here is persisted or sent to the backend), so it's wired once
// against the fixed set of .faq-item elements in the HTML rather than being
// generated from a data list.
document.querySelectorAll<HTMLElement>(".faq-item").forEach((item) => {
  const question = item.querySelector(".faq-q");
  question?.addEventListener("click", () => {
    const wasOpen = item.classList.contains("open");
    document.querySelectorAll<HTMLElement>(".faq-item").forEach((other) => {
      other.classList.remove("open");
      const symbol = other.querySelector(".faq-q-symbol");
      if (symbol) symbol.textContent = "+";
    });
    if (!wasOpen) {
      item.classList.add("open");
      const symbol = item.querySelector(".faq-q-symbol");
      if (symbol) symbol.textContent = "−";
    }
  });
});

window.backend.on("status", (message) => {
  lastStatus = message as typeof lastStatus;
  updateToggleButton();
});

window.backend.on("click_log_path", (message) => {
  const { path: logPath, isDefault } = message as { path: string; isDefault: boolean };
  renderClickLogPath(logPath, isDefault);
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
