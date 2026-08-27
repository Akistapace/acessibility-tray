// Direct Node successor of backend.py's BackendServer: owns a
// TrackingEngine (Task 10) and handles command dispatch plus frame/status
// push loops. Drop-in replacement for BackendProcess -- emits "message"
// events shaped exactly like the old stdio protocol messages and exposes
// .send(command), the same two members apps/desktop/src/main/ipc/relay.ts's
// wireBackendRelay already expects.
import { EventEmitter } from "node:events";
import * as clickLog from "./clickLog.service";
import { configFromDict, configToDict, cursorFromDict, GESTURE_NAMES, loadConfig, saveConfig, type AppConfig } from "./config.service";
// Only applyCursor is used here -- it already internally delegates to
// restoreCursor for the all-defaults case, so set_cursor_theme never needs
// to call restoreCursor directly. restoreCursor is wired at the app-lifecycle
// level instead (see index.ts's before-quit / camera-failure paths).
import { applyCursor } from "./cursorTheme.service";
import { triggerProgress } from "./gestures.service";
import type { TrackingEngine } from "./trackingEngine.service";
import type { TrackingFrame } from "@facemesh-mouse/shared";

const STATUS_POLL_INTERVAL_MS = 200;

export interface BackendServerDeps {
  engine: TrackingEngine;
  config: AppConfig;
  configPath?: string;
  toggleTouchKeyboard?: () => Promise<boolean>;
  toggleVoiceTyping?: () => Promise<void>;
}

export class BackendServer extends EventEmitter {
  config: AppConfig;
  previewEnabled = false;
  highlightedGesture: string | null = null;

  private readonly engine: TrackingEngine;
  private readonly configPath: string;
  private readonly toggleTouchKeyboardImpl: () => Promise<boolean>;
  private readonly toggleVoiceTypingImpl: () => Promise<void>;
  private frameSeq = 0;
  private frameInFlight = false;
  private lastStatusJson: string | null = null;
  private statusTimer: ReturnType<typeof setInterval> | null = null;
  private previewListeners: Array<(enabled: boolean) => void> = [];
  private highlightListeners: Array<(gesture: string | null) => void> = [];

  constructor(deps: BackendServerDeps) {
    super();
    this.engine = deps.engine;
    this.config = deps.config;
    this.configPath = deps.configPath ?? "config.json";
    this.toggleTouchKeyboardImpl = deps.toggleTouchKeyboard ?? (async () => false);
    this.toggleVoiceTypingImpl = deps.toggleVoiceTyping ?? (async () => {});
  }

  start(): void {
    this.statusTimer = setInterval(() => this.pushStatusIfChanged(), STATUS_POLL_INTERVAL_MS);
  }

  stop(): void {
    if (this.statusTimer) clearInterval(this.statusTimer);
    this.statusTimer = null;
  }

  onPreviewChange(callback: (enabled: boolean) => void): void {
    this.previewListeners.push(callback);
  }

  onHighlightChange(callback: (gesture: string | null) => void): void {
    this.highlightListeners.push(callback);
  }

  private pushStatusIfChanged(): void {
    const current = {
      control_enabled: this.engine.controlEnabled,
      paused: this.engine.paused,
      no_face: this.engine.noFace,
      yielded: this.engine.yielded,
    };
    const currentJson = JSON.stringify(current);
    if (currentJson !== this.lastStatusJson) {
      this.emit("message", { type: "status", ...current });
      this.lastStatusJson = currentJson;
    }
  }

  async onTrackingFrame(frame: TrackingFrame): Promise<void> {
    // Guards against overlapping in-flight frames: the renderer fires
    // tracking:frame IPC messages with no acknowledgement, and
    // MouseController.moveCursor's awaited getPosition()/setPosition() pair
    // could otherwise interleave across two frames and spuriously trigger a
    // control yield. Drop the frame rather than queueing it -- don't process
    // frames faster than they can be handled.
    if (this.frameInFlight) return;
    this.frameInFlight = true;
    try {
      await this.engine.onFrame(frame);
      // One malformed frame's preview/progress encoding must never take down
      // whatever loop is feeding us frames -- mirrors backend.py's
      // _frame_loop try/except around _encode_frame + send.
      try {
        if (this.previewEnabled && frame.previewJpegBase64) {
          const gesture_progress: Record<string, number> = {};
          for (const [name, gestureCfg] of Object.entries(this.config.gestures)) {
            gesture_progress[name] = frame.metrics ? triggerProgress(name, frame.metrics, gestureCfg.threshold) : 0.0;
          }
          this.emit("message", {
            type: "frame",
            jpeg_b64: frame.previewJpegBase64,
            gesture_progress,
            seq: this.frameSeq++,
          });
        }
      } catch (exc) {
        console.error(`facemesh-mouse: frame push failed (${exc})`);
      }
    } finally {
      this.frameInFlight = false;
    }
  }

  async send(command: Record<string, unknown>): Promise<void> {
    const type = command.type as string | undefined;
    try {
      switch (type) {
        case "set_preview":
          this.previewEnabled = Boolean(command.enabled);
          for (const listener of this.previewListeners) listener(this.previewEnabled);
          break;
        case "highlight_gesture": {
          const gesture = command.gesture as string | null;
          this.highlightedGesture = gesture && (GESTURE_NAMES as readonly string[]).includes(gesture) ? gesture : null;
          for (const listener of this.highlightListeners) listener(this.highlightedGesture);
          break;
        }
        case "start":
          this.engine.controlEnabled = true;
          break;
        case "stop":
          this.engine.controlEnabled = false;
          break;
        case "pause":
          this.engine.paused = true;
          break;
        case "resume":
          this.engine.paused = false;
          break;
        case "set_cursor_theme": {
          this.config.cursor = cursorFromDict({
            size_px: command.size_px,
            mode: command.mode,
            custom_color: command.custom_color,
          });
          applyCursor(this.config.cursor.size_px, this.config.cursor.mode, this.config.cursor.custom_color);
          break;
        }
        case "update_config": {
          this.config = configFromDict((command.config as Record<string, unknown>) ?? {});
          this.engine.updateConfig(this.config);
          this.syncClickLogging(this.config);
          break;
        }
        case "save_config": {
          const onDisk = loadConfig(this.configPath);
          const onDiskDict = configToDict(onDisk) as Record<string, unknown>;
          const payload = (command.config as Record<string, unknown>) ?? {};
          const merged: Record<string, unknown> = { ...onDiskDict, ...payload };
          if (payload.calibration) {
            merged.calibration = { ...(onDiskDict.calibration as object), ...(payload.calibration as object) };
          }
          if (payload.action_buttons) {
            merged.action_buttons = { ...(onDiskDict.action_buttons as object), ...(payload.action_buttons as object) };
          }
          if (payload.cursor) {
            merged.cursor = { ...(onDiskDict.cursor as object), ...(payload.cursor as object) };
          }
          const saved = configFromDict(merged);
          saveConfig(this.configPath, saved);
          // Salvar must apply live, not just persist to disk -- otherwise a
          // gesture's action reassigned mid-session (e.g. to left_drag,
          // scroll_up/down, or freeze_cursor) silently keeps running the OLD
          // action until the engine is restarted, while the config UI (which
          // re-reads this same broadcast) already shows the new one.
          this.config = saved;
          this.engine.updateConfig(this.config);
          this.syncClickLogging(this.config);
          this.emit("message", { type: "config", config: configToDict(saved) });
          break;
        }
        case "open_keyboard": {
          const x = Number(command.x ?? 0);
          const y = Number(command.y ?? 0);
          const opened = await this.toggleTouchKeyboardImpl();
          this.emit("message", { type: "keyboard_result", opened, x, y });
          break;
        }
        case "open_voice_typing":
          await this.toggleVoiceTypingImpl();
          break;
        case "get_config":
          this.emit("message", { type: "config", config: configToDict(this.config) });
          break;
        default:
          break;
      }
    } catch (exc) {
      console.error(`facemesh-mouse: command ${type ?? "?"} failed (${exc})`);
    }
  }

  private syncClickLogging(config: AppConfig): void {
    try {
      if (config.calibration.click_logging_enabled) clickLog.enable();
      else clickLog.disable();
    } catch (exc) {
      console.error(`facemesh-mouse: click log setup failed (${exc})`);
    }
  }
}
