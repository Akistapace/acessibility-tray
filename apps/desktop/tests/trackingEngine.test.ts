import { describe, expect, it } from "vitest";
import { TrackingEngine } from "../src/main/services/trackingEngine.service";
import { defaultConfig } from "../src/main/services/config.service";
import type { MouseDriver } from "../src/main/services/mouseController.service";
import type { FaceMetrics, TrackingFrame } from "@facemesh-mouse/shared";

class FakeMouseDriver implements MouseDriver {
  position: [number, number];
  clicks: Array<["left" | "right", 1 | 2]> = [];
  presses: string[] = [];
  releases: string[] = [];
  scrolls: Array<[number, number]> = [];
  constructor(start: [number, number] = [500, 500]) { this.position = start; }
  async getPosition() { return this.position; }
  async setPosition(pos: [number, number]) { this.position = pos; }
  async click(button: "left" | "right", count: 1 | 2) { this.clicks.push([button, count]); }
  async pressButton(button: "left") { this.presses.push(button); }
  async releaseButton(button: "left") { this.releases.push(button); }
  async scroll(dx: number, dy: number) { this.scrolls.push([dx, dy]); }
}

function metrics(overrides: Partial<FaceMetrics> = {}): FaceMetrics {
  return {
    noseX: 0.5, noseY: 0.5, earA: 0.3, earB: 0.3, mouthOpenRatio: 0.1,
    eyebrowRaiseA: 0.05, eyebrowRaiseB: 0.05, mouthShiftRatio: 0.0, landmarks: [],
    ...overrides,
  };
}

function frame(m: FaceMetrics | null, movement: [number, number] = [0, 0]): TrackingFrame {
  return { metrics: m, movement, previewJpegBase64: null };
}

describe("TrackingEngine", () => {
  it("does not move the mouse while control is disabled", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const engine = new TrackingEngine(defaultConfig(), driver, [1000, 1000]);

    await engine.onFrame(frame(metrics(), [10, 0]));

    expect(driver.position).toEqual([500, 500]);
  });

  it("reanchors on the first active frame, then drives the cursor", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const engine = new TrackingEngine(defaultConfig(), driver, [1000, 1000]);
    engine.controlEnabled = true;

    await engine.onFrame(frame(metrics(), [4.0, 0.0]));

    expect(driver.position[0]).toBeGreaterThan(500);
  });

  it("releases a held drag when control is paused mid-hold", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const config = defaultConfig();
    config.gestures.blink_a = { action: "left_drag", threshold: 0.2, cooldown_ms: 0, hold_ms: 0 };
    const engine = new TrackingEngine(config, driver, [1000, 1000]);
    engine.controlEnabled = true;

    await engine.onFrame(frame(metrics({ earA: 0.1, earB: 0.3 }), [0, 0])); // fires the drag press
    expect(driver.presses).toHaveLength(1);

    engine.paused = true;
    await engine.onFrame(frame(metrics({ earA: 0.1, earB: 0.3 }), [0, 0]));

    expect(driver.releases).toHaveLength(1);
  });

  it("releases held state and sets noFace when the face is lost", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const config = defaultConfig();
    config.gestures.blink_a = { action: "left_drag", threshold: 0.2, cooldown_ms: 0, hold_ms: 0 };
    const engine = new TrackingEngine(config, driver, [1000, 1000]);
    engine.controlEnabled = true;

    await engine.onFrame(frame(metrics({ earA: 0.1, earB: 0.3 }), [0, 0]));
    expect(driver.presses).toHaveLength(1);

    await engine.onFrame(frame(null));

    expect(engine.noFace).toBe(true);
    expect(driver.releases).toHaveLength(1);
  });

  it("skips dwell evaluation while the cursor is frozen", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const config = defaultConfig();
    config.calibration.dwell_click_enabled = true;
    config.calibration.dwell_time_s = 0.0; // would fire immediately if evaluated
    config.gestures.eyebrow_both = { action: "freeze_cursor", threshold: 0.1, cooldown_ms: 0, hold_ms: 0 };
    const engine = new TrackingEngine(config, driver, [1000, 1000]);
    engine.controlEnabled = true;

    await engine.onFrame(frame(metrics({ eyebrowRaiseA: 0.2, eyebrowRaiseB: 0.2 }), [0, 0])); // freezes

    expect(driver.clicks).toEqual([]); // dwell never evaluated while frozen
  });
});
