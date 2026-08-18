import { describe, expect, it } from "vitest";
import { accelerate, clamp } from "../src/modules/mouseController";

describe("accelerate", () => {
  it("returns zero for zero movement", () => {
    expect(accelerate(0.0, 0.5)).toBe(0.0);
  });

  it("preserves sign", () => {
    expect(accelerate(-0.05, 0.5)).toBeLessThan(0);
    expect(accelerate(0.05, 0.5)).toBeGreaterThan(0);
  });

  it("is a linear pass-through at acceleration 0", () => {
    expect(accelerate(0.037, 0.0)).toBeCloseTo(0.037);
  });

  it("damps small movements more than large ones", () => {
    const small = 0.01, large = 0.2;
    const smallRatio = accelerate(small, 0.5) / small;
    const largeRatio = accelerate(large, 0.5) / large;
    expect(smallRatio).toBeLessThan(largeRatio);
  });
});

describe("clamp", () => {
  it("clamps to the given range", () => {
    expect(clamp(5, 0, 10)).toBe(5);
    expect(clamp(-1, 0, 10)).toBe(0);
    expect(clamp(11, 0, 10)).toBe(10);
  });
});

import { MouseController, type MouseDriver } from "../src/modules/mouseController";
import type { AppConfig, CalibrationConfig } from "../src/modules/config";

class FakeMouseDriver implements MouseDriver {
  position: [number, number];
  clicks: Array<["left" | "right", 1 | 2]> = [];
  presses: string[] = [];
  releases: string[] = [];
  scrolls: Array<[number, number]> = [];
  constructor(start: [number, number] = [500, 500]) {
    this.position = start;
  }
  async getPosition() { return this.position; }
  async setPosition(pos: [number, number]) { this.position = pos; }
  async click(button: "left" | "right", count: 1 | 2) { this.clicks.push([button, count]); }
  async pressButton(button: "left") { this.presses.push(button); }
  async releaseButton(button: "left") { this.releases.push(button); }
  async scroll(dx: number, dy: number) { this.scrolls.push([dx, dy]); }
}

function calibration(overrides: Partial<CalibrationConfig> = {}): CalibrationConfig {
  return {
    sensitivity_x: 0.025, sensitivity_y: 0.05, acceleration: 0.0,
    motion_threshold_px: 0.0, yield_resume_after_s: 3.0,
    click_logging_enabled: true, dwell_click_enabled: false, dwell_time_s: 1.0,
    ...overrides,
  };
}

function testConfig(cal: Partial<CalibrationConfig> = {}, gestures: AppConfig["gestures"] = {}): AppConfig {
  return { calibration: calibration(cal), gestures, action_buttons: { x: null, y: null } };
}

class FakeClock {
  t = 0;
  tick = () => this.t;
}

describe("MouseController.moveCursor", () => {
  it("moves x without inverting", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig(), [1000, 1000], driver);
    await controller.reanchor();

    await controller.moveCursor(4.0, 0.0); // 4 * 0.025 sensitivity = 0.1 -> 100px of a 1000px screen

    expect(Math.abs(driver.position[0] - 600)).toBeLessThanOrEqual(1);
    expect(Math.abs(driver.position[1] - 500)).toBeLessThanOrEqual(1);
  });

  it("moves y without inverting", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig(), [1000, 1000], driver);
    await controller.reanchor();

    await controller.moveCursor(0.0, 2.0); // 2 * 0.05 = 0.1 -> +100px

    expect(Math.abs(driver.position[1] - 600)).toBeLessThanOrEqual(1);
  });

  it("ignores non-finite movement", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig(), [1000, 1000], driver);
    await controller.reanchor();

    await controller.moveCursor(NaN, 0.0);

    expect(driver.position).toEqual([500, 500]);
  });

  it("zeroes a movement under the motion threshold", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig({ motion_threshold_px: 50.0 }), [1000, 1000], driver);
    await controller.reanchor();

    await controller.moveCursor(0.4, 0.0); // 0.4 * 0.025 * 1000 = 10px, under the 50px threshold

    expect(driver.position).toEqual([500, 500]);
  });

  it("clamps the cursor to the screen", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig(), [1000, 1000], driver);
    await controller.reanchor();

    await controller.moveCursor(1000.0, 1000.0);

    expect(driver.position[0]).toBeGreaterThanOrEqual(0);
    expect(driver.position[0]).toBeLessThanOrEqual(999);
  });

  it("yields when the cursor diverges from the last write", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig(), [1000, 1000], driver);
    await controller.reanchor();

    driver.position = [700, 500]; // simulated physical-mouse touch
    await controller.moveCursor(4.0, 0.0);

    expect(controller.yielded).toBe(true);
    expect(driver.position).toEqual([700, 500]);
  });

  it("does not mistake small drift for a physical move", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig(), [1000, 1000], driver);
    await controller.reanchor();

    driver.position = [501, 500]; // within YIELD_DETECT_PX
    await controller.moveCursor(4.0, 0.0);

    expect(controller.yielded).toBe(false);
  });

  it("resumes from yield with no jump once the quiet period elapses", async () => {
    const clock = new FakeClock();
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig({ yield_resume_after_s: 3.0 }), [1000, 1000], driver, clock.tick);
    await controller.reanchor();

    driver.position = [700, 500];
    await controller.moveCursor(0.0, 0.0); // enters yielded at t=0

    clock.t = 3.1;
    await controller.moveCursor(0.0, 0.0);

    expect(driver.position).toEqual([700, 500]); // resume must not move the cursor
  });
});

describe("MouseController.evaluateDwell", () => {
  it("never fires while disabled", async () => {
    const clock = new FakeClock();
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(testConfig(), [1000, 1000], driver, clock.tick);
    await controller.reanchor();

    clock.t = 10.0;
    await controller.evaluateDwell();

    expect(driver.clicks).toEqual([]);
  });

  it("fires after holding still for the configured time, once", async () => {
    const clock = new FakeClock();
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(
      testConfig({ dwell_click_enabled: true, dwell_time_s: 1.0 }), [1000, 1000], driver, clock.tick
    );
    await controller.reanchor();

    await controller.evaluateDwell(); // starts the timer at t=0
    clock.t = 0.9;
    await controller.evaluateDwell();
    expect(driver.clicks).toEqual([]);

    clock.t = 1.1;
    await controller.evaluateDwell();
    expect(driver.clicks).toHaveLength(1);

    clock.t = 3.0; // still stationary -- must not repeat
    await controller.evaluateDwell();
    expect(driver.clicks).toHaveLength(1);
  });

  it("fires again after the cursor moves away and settles", async () => {
    const clock = new FakeClock();
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(
      testConfig({ dwell_click_enabled: true, dwell_time_s: 1.0 }), [1000, 1000], driver, clock.tick
    );
    await controller.reanchor();

    await controller.evaluateDwell();
    clock.t = 1.1;
    await controller.evaluateDwell();
    expect(driver.clicks).toHaveLength(1);

    driver.position = [700, 500];
    clock.t = 1.2;
    await controller.evaluateDwell();
    clock.t = 2.3;
    await controller.evaluateDwell();

    expect(driver.clicks).toHaveLength(2);
  });

  it("a stale dwell timer does not survive reanchor", async () => {
    const clock = new FakeClock();
    const driver = new FakeMouseDriver([500, 500]);
    const controller = new MouseController(
      testConfig({ dwell_click_enabled: true, dwell_time_s: 1.0 }), [1000, 1000], driver, clock.tick
    );
    await controller.reanchor();

    await controller.evaluateDwell(); // timer running at t=0, unfired
    clock.t = 5.0;
    await controller.reanchor(); // e.g. resuming from pause

    await controller.evaluateDwell(); // only restarts the timer, at t=5.0
    expect(driver.clicks).toEqual([]);
  });
});

describe("MouseController actions", () => {
  it("fireAction invokes the callback and clicks", async () => {
    const driver = new FakeMouseDriver();
    const calls: unknown[] = [];
    const config = testConfig({}, { blink_a: { action: "left_click", threshold: 0.2, cooldown_ms: 0, hold_ms: 0 } });
    const controller = new MouseController(config, [1000, 1000], driver, undefined, (...args) => calls.push(args));

    await controller.fireAction("blink_a");

    expect(driver.clicks).toHaveLength(1);
    expect(calls).toHaveLength(1);
  });

  it("left_drag presses without clicking, release_action releases it", async () => {
    const driver = new FakeMouseDriver();
    const config = testConfig({}, { blink_a: { action: "left_drag", threshold: 0.2, cooldown_ms: 0, hold_ms: 0 } });
    const controller = new MouseController(config, [1000, 1000], driver);

    await controller.fireAction("blink_a");
    expect(driver.presses).toHaveLength(1);
    expect(driver.clicks).toEqual([]);

    await controller.releaseAction("blink_a");
    expect(driver.releases).toHaveLength(1);
  });

  it("freeze_cursor toggles frozen and stops moveCursor from moving the mouse", async () => {
    const driver = new FakeMouseDriver([500, 500]);
    const config = testConfig({}, { eyebrow_both: { action: "freeze_cursor", threshold: 0.1, cooldown_ms: 0, hold_ms: 0 } });
    const controller = new MouseController(config, [1000, 1000], driver);
    await controller.reanchor();

    await controller.fireAction("eyebrow_both");
    await controller.moveCursor(4.0, 0.0);
    expect(driver.position).toEqual([500, 500]);
    expect(controller.frozen).toBe(true);

    await controller.fireAction("eyebrow_both"); // second fire toggles back off
    expect(controller.frozen).toBe(false);
  });

  it("releaseAllHolds releases a pressed drag and unfreezes", async () => {
    const driver = new FakeMouseDriver();
    const config = testConfig({}, {
      blink_a: { action: "left_drag", threshold: 0.2, cooldown_ms: 0, hold_ms: 0 },
      eyebrow_both: { action: "freeze_cursor", threshold: 0.1, cooldown_ms: 0, hold_ms: 0 },
    });
    const controller = new MouseController(config, [1000, 1000], driver);

    await controller.fireAction("blink_a");
    await controller.fireAction("eyebrow_both");
    await controller.releaseAllHolds();

    expect(driver.releases).toHaveLength(1);
    expect(controller.frozen).toBe(false);
  });
});
