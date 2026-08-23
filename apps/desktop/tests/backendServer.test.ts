import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { BackendServer } from "../src/main/services/backendServer";
import { TrackingEngine } from "../src/main/services/trackingEngine.service";
import * as configMod from "../src/main/services/config.service";
import type { MouseDriver } from "../src/main/services/mouseController.service";

// Mock cursorTheme.service entirely -- set_cursor_theme's job is to update
// backendServer.config.cursor and delegate to applyCursor with the resolved
// values; it must never touch the real registry / SystemParametersInfoW in a
// unit test. applyCursor's own registry/no-op behavior is covered by
// cursorTheme.test.ts.
const applyCursorMock = vi.fn();
vi.mock("../src/main/services/cursorTheme.service", () => ({
  applyCursor: (...args: unknown[]) => applyCursorMock(...args),
}));

class FakeMouseDriver implements MouseDriver {
  position: [number, number] = [500, 500];
  async getPosition() { return this.position; }
  async setPosition(pos: [number, number]) { this.position = pos; }
  async click() {}
  async pressButton() {}
  async releaseButton() {}
  async scroll() {}
}

function waitForMessage(server: BackendServer, type: string): Promise<Record<string, unknown>> {
  return new Promise((resolve) => {
    server.on("message", (message: Record<string, unknown>) => {
      if (message.type === type) resolve(message);
    });
  });
}

let tmpDir: string;
beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "facemesh-backend-"));
  applyCursorMock.mockClear();
});
afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("BackendServer.send", () => {
  it("start/stop set and clear engine.controlEnabled", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });

    await server.send({ type: "start" });
    expect(engine.controlEnabled).toBe(true);

    await server.send({ type: "stop" });
    expect(engine.controlEnabled).toBe(false);
  });

  it("pause/resume set and clear engine.paused", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });

    await server.send({ type: "pause" });
    expect(engine.paused).toBe(true);
    await server.send({ type: "resume" });
    expect(engine.paused).toBe(false);
  });

  it("set_preview toggles previewEnabled", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });

    await server.send({ type: "set_preview", enabled: true });
    expect(server.previewEnabled).toBe(true);
    await server.send({ type: "set_preview", enabled: false });
    expect(server.previewEnabled).toBe(false);
  });

  it("highlight_gesture accepts a known gesture name and rejects unknown ones", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });

    await server.send({ type: "highlight_gesture", gesture: "blink_a" });
    expect(server.highlightedGesture).toBe("blink_a");

    await server.send({ type: "highlight_gesture", gesture: "not_a_real_gesture" });
    expect(server.highlightedGesture).toBeNull();

    await server.send({ type: "highlight_gesture", gesture: "mouth_open" });
    expect(server.highlightedGesture).toBe("mouth_open");
    await server.send({ type: "highlight_gesture", gesture: null });
    expect(server.highlightedGesture).toBeNull();
  });

  it("onHighlightChange listeners fire with the resolved gesture on every highlight_gesture command", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });
    const seen: Array<string | null> = [];
    server.onHighlightChange((gesture) => seen.push(gesture));

    await server.send({ type: "highlight_gesture", gesture: "eyebrow_both" });
    await server.send({ type: "highlight_gesture", gesture: "bogus" });
    await server.send({ type: "highlight_gesture", gesture: null });

    expect(seen).toEqual(["eyebrow_both", null, null]);
  });

  it("update_config applies to the engine and updates server.config", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });
    const next = configMod.defaultConfig();
    next.calibration.sensitivity_x = 0.09;

    await server.send({ type: "update_config", config: configMod.configToDict(next) });

    expect(server.config.calibration.sensitivity_x).toBe(0.09);
  });

  it("set_cursor_theme updates server.config.cursor and calls applyCursor with the resolved values", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });

    await server.send({ type: "set_cursor_theme", size_px: 64, mode: "custom", custom_color: "#ff00ff" });

    expect(server.config.cursor).toEqual({ size_px: 64, mode: "custom", custom_color: "#ff00ff" });
    expect(applyCursorMock).toHaveBeenCalledWith(64, "custom", "#ff00ff");
  });

  it("set_cursor_theme clamps size_px and falls back an invalid mode, mirroring cursorFromDict", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });

    await server.send({ type: "set_cursor_theme", size_px: 500, mode: "not_a_real_mode", custom_color: "#abcabc" });

    expect(server.config.cursor).toEqual({ size_px: 96, mode: "default", custom_color: "#abcabc" });
    expect(applyCursorMock).toHaveBeenCalledWith(96, "default", "#abcabc");
  });

  it("save_config writes to disk and merges a partial payload onto the existing file", async () => {
    const file = path.join(tmpDir, "config.json");
    const seed = configMod.defaultConfig();
    seed.calibration.sensitivity_x = 0.09;
    configMod.saveConfig(file, seed);

    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig(), configPath: file });

    await server.send({ type: "save_config", config: { action_buttons: { x: 120.0, y: 640.0 } } });

    const reloaded = configMod.loadConfig(file);
    expect(reloaded.calibration.sensitivity_x).toBe(0.09);
    expect(reloaded.action_buttons.x).toBe(120.0);
  });

  it("save_config merges a partial cursor payload onto the existing file", async () => {
    const file = path.join(tmpDir, "config.json");
    const seed = configMod.defaultConfig();
    seed.cursor = { size_px: 48, mode: "white", custom_color: "#111111" };
    configMod.saveConfig(file, seed);

    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig(), configPath: file });

    await server.send({ type: "save_config", config: { cursor: { mode: "custom" } } });

    const reloaded = configMod.loadConfig(file);
    expect(reloaded.cursor).toEqual({ size_px: 48, mode: "custom", custom_color: "#111111" });
  });

  it("save_config merges a partial custom_keyboard payload onto the existing file", async () => {
    const file = path.join(tmpDir, "config.json");
    const seed = configMod.defaultConfig();
    seed.custom_keyboard = { x: 10, y: 20, compact: false };
    configMod.saveConfig(file, seed);

    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig(), configPath: file });

    await server.send({ type: "save_config", config: { custom_keyboard: { compact: true } } });

    const reloaded = configMod.loadConfig(file);
    expect(reloaded.custom_keyboard).toEqual({ x: 10, y: 20, compact: true });
  });

  it("save_config broadcasts the saved config so other windows learn of the change without restarting", async () => {
    const file = path.join(tmpDir, "config.json");
    configMod.saveConfig(file, configMod.defaultConfig());

    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig(), configPath: file });
    const messagePromise = waitForMessage(server, "config");

    await server.send({
      type: "save_config",
      config: { calibration: { keyboard_button_enabled: false } },
    });

    const reloaded = configMod.loadConfig(file);
    expect(await messagePromise).toEqual({ type: "config", config: configMod.configToDict(reloaded) });
    expect(reloaded.calibration.keyboard_button_enabled).toBe(false);
  });

  it("open_keyboard calls the injected openKeyboard and always reports opened:true", async () => {
    let called = false;
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({
      engine, config: configMod.defaultConfig(),
      openKeyboard: () => { called = true; },
    });
    const messagePromise = waitForMessage(server, "keyboard_result");

    await server.send({ type: "open_keyboard", x: 100, y: 200 });

    expect(await messagePromise).toEqual({ type: "keyboard_result", opened: true, x: 100, y: 200 });
    expect(called).toBe(true);
  });

  it("open_keyboard still reports opened:true with no openKeyboard dep injected", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });
    const messagePromise = waitForMessage(server, "keyboard_result");

    await server.send({ type: "open_keyboard", x: 1, y: 2 });

    expect(await messagePromise).toEqual({ type: "keyboard_result", opened: true, x: 1, y: 2 });
  });

  it("open_voice_typing calls the injected toggle", async () => {
    let called = false;
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({
      engine, config: configMod.defaultConfig(),
      toggleVoiceTyping: async () => { called = true; },
    });

    await server.send({ type: "open_voice_typing" });

    expect(called).toBe(true);
  });

  it("get_config sends the current config", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const config = configMod.defaultConfig();
    config.calibration.sensitivity_x = 0.06;
    const server = new BackendServer({ engine, config });
    const messagePromise = waitForMessage(server, "config");

    await server.send({ type: "get_config" });

    expect(await messagePromise).toEqual({ type: "config", config: configMod.configToDict(config) });
  });

  it("ignores an unknown command type without throwing", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });

    await expect(server.send({ type: "not_a_real_command" })).resolves.toBeUndefined();
  });

  it("catches a failing handler instead of throwing", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });

    await expect(
      server.send({ type: "update_config", config: null as unknown as Record<string, unknown> })
    ).resolves.toBeUndefined();
  });
});

describe("BackendServer.onTrackingFrame", () => {
  it("emits a frame message with gesture_progress for every gesture when preview is enabled", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const config = configMod.defaultConfig();
    const server = new BackendServer({ engine, config });
    await server.send({ type: "set_preview", enabled: true });
    const messagePromise = waitForMessage(server, "frame");

    await server.onTrackingFrame({ metrics: null, movement: [0, 0], previewJpegBase64: "abc==" });

    const message = await messagePromise;
    expect(message.type).toBe("frame");
    expect(Object.keys(message.gesture_progress as object).sort()).toEqual([...configMod.GESTURE_NAMES].sort());
    expect(Object.values(message.gesture_progress as Record<string, number>).every((v) => v === 0.0)).toBe(true);
  });
});
