import { describe, expect, it } from "vitest";
import { GestureEngine, triggerProgress } from "../src/main/services/gestures.service";
import type { AppConfig, GestureConfig } from "../src/main/services/config.service";
import type { FaceMetrics } from "@facemesh-mouse/shared";

function metrics(overrides: Partial<FaceMetrics> = {}): FaceMetrics {
  return {
    noseX: 0.5, noseY: 0.5,
    earA: 0.3, earB: 0.3,
    mouthOpenRatio: 0.1,
    eyebrowRaiseA: 0.05, eyebrowRaiseB: 0.05,
    mouthShiftRatio: 0.0,
    landmarks: [],
    ...overrides,
  };
}

function gestureConfig(action: string, threshold: number, cooldown_ms = 0, hold_ms = 0): GestureConfig {
  return { action, threshold, cooldown_ms, hold_ms };
}

function config(overrides: Partial<Record<string, GestureConfig>> = {}, hold_ms = 0): AppConfig {
  const gestures: Record<string, GestureConfig> = {
    blink_a: gestureConfig("left_click", 0.2, 0, hold_ms),
    blink_b: gestureConfig("right_click", 0.2, 0, hold_ms),
    blink_both: gestureConfig("none", 0.2, 0, hold_ms),
    eyebrow_a: gestureConfig("none", 0.1, 0, hold_ms),
    eyebrow_b: gestureConfig("none", 0.1, 0, hold_ms),
    eyebrow_both: gestureConfig("none", 0.1, 0, hold_ms),
    mouth_open: gestureConfig("double_click", 0.3, 0, hold_ms),
    mouth_left: gestureConfig("none", 0.05, 0, hold_ms),
    mouth_right: gestureConfig("none", 0.05, 0, hold_ms),
    ...overrides,
  };
  return { calibration: {} as AppConfig["calibration"], gestures, action_buttons: { x: null, y: null } };
}

class FakeClock {
  t = 0;
  tick = () => this.t;
}

describe("GestureEngine.evaluate", () => {
  it("fires blink_a once on transition, then again after release/rehold", () => {
    const clock = new FakeClock();
    const engine = new GestureEngine(config(), clock.tick);

    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual(["blink_a"]);
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual([]);

    engine.evaluate(metrics({ earA: 0.3, earB: 0.3 }));
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual(["blink_a"]);
  });

  it("prefers blink_both over the single-eye condition", () => {
    const engine = new GestureEngine(config(), new FakeClock().tick);
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.1 }))).toEqual(["blink_both"]);
  });

  it("requires a closed mouth for lateral mouth gestures", () => {
    const engine = new GestureEngine(config(), new FakeClock().tick);
    expect(engine.evaluate(metrics({ mouthShiftRatio: -0.2, mouthOpenRatio: 0.5 }))).toEqual(["mouth_open"]);
    expect(engine.evaluate(metrics({ mouthShiftRatio: -0.2, mouthOpenRatio: 0.05 }))).toEqual(["mouth_left"]);
  });

  it("blocks retrigger during cooldown, then fires again once it elapses", () => {
    const clock = new FakeClock();
    const engine = new GestureEngine(
      config({ blink_a: gestureConfig("left_click", 0.2, 1000, 0) }),
      clock.tick
    );

    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual(["blink_a"]);
    engine.evaluate(metrics({ earA: 0.3, earB: 0.3 }));
    clock.t = 0.5;
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual([]);
    engine.evaluate(metrics({ earA: 0.3, earB: 0.3 }));
    clock.t = 1.1;
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual(["blink_a"]);
  });

  it("does not let a natural asynchronous two-eye blink fire a single-eye gesture with a hold time", () => {
    const clock = new FakeClock();
    const engine = new GestureEngine(config({}, 400), clock.tick);

    clock.t = 0.0;
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual([]);
    clock.t = 0.08;
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.1 }))).toEqual([]);
    clock.t = 0.14;
    expect(engine.evaluate(metrics({ earA: 0.3, earB: 0.3 }))).toEqual([]);
    clock.t = 1.0;
    expect(engine.evaluate(metrics({ earA: 0.3, earB: 0.3 }))).toEqual([]);
  });

  it("scroll actions repeat at the cooldown cadence while held", () => {
    const clock = new FakeClock();
    const engine = new GestureEngine(
      config({ blink_a: gestureConfig("scroll_up", 0.2, 200, 0) }),
      clock.tick
    );

    clock.t = 0.0;
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual(["blink_a"]);
    clock.t = 0.1;
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual([]);
    clock.t = 0.2;
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual(["blink_a"]);
  });

  it("drag actions fire on hold-complete and report a debounced release", () => {
    const clock = new FakeClock();
    const engine = new GestureEngine(
      config({ blink_a: gestureConfig("left_drag", 0.2, 0, 400) }),
      clock.tick
    );

    clock.t = 0.0;
    engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }));
    clock.t = 0.4;
    expect(engine.evaluate(metrics({ earA: 0.1, earB: 0.3 }))).toEqual(["blink_a"]);
    expect(engine.lastReleased).toEqual([]);

    clock.t = 0.8;
    engine.evaluate(metrics({ earA: 0.3, earB: 0.3 }));
    clock.t = 1.21; // 410ms of continuous release
    engine.evaluate(metrics({ earA: 0.3, earB: 0.3 }));
    expect(engine.lastReleased).toEqual(["blink_a"]);
  });

  it("a single-frame dip below threshold does not drop a held drag", () => {
    const clock = new FakeClock();
    const engine = new GestureEngine(
      config({ mouth_open: gestureConfig("left_drag", 0.35, 0, 400) }),
      clock.tick
    );

    clock.t = 0.0;
    engine.evaluate(metrics({ mouthOpenRatio: 0.5 }));
    clock.t = 0.4;
    expect(engine.evaluate(metrics({ mouthOpenRatio: 0.5 }))).toEqual(["mouth_open"]);

    clock.t = 0.5;
    expect(engine.evaluate(metrics({ mouthOpenRatio: 0.2 }))).toEqual([]);
    expect(engine.lastReleased).toEqual([]);
  });

  it("freeze_cursor fires once per hold like a click, with no release event", () => {
    const clock = new FakeClock();
    const engine = new GestureEngine(
      config({ eyebrow_both: gestureConfig("freeze_cursor", 0.1, 0, 200) }),
      clock.tick
    );

    clock.t = 0.0;
    expect(engine.evaluate(metrics({ eyebrowRaiseA: 0.2, eyebrowRaiseB: 0.2 }))).toEqual([]);
    clock.t = 0.2;
    expect(engine.evaluate(metrics({ eyebrowRaiseA: 0.2, eyebrowRaiseB: 0.2 }))).toEqual(["eyebrow_both"]);
    clock.t = 0.5;
    expect(engine.evaluate(metrics({ eyebrowRaiseA: 0.2, eyebrowRaiseB: 0.2 }))).toEqual([]);
    expect(engine.lastReleased).toEqual([]);
  });
});

describe("triggerProgress", () => {
  it("reaches 1.0 exactly at threshold, for both above- and below-threshold gestures", () => {
    expect(triggerProgress("mouth_open", metrics({ mouthOpenRatio: 0.35 }), 0.35)).toBeCloseTo(1.0);
    expect(triggerProgress("blink_a", metrics({ earA: 0.21 }), 0.21)).toBeCloseTo(1.0);
  });

  it("stays within the unit range", () => {
    expect(triggerProgress("blink_a", metrics({ earA: 0.01 }), 0.21)).toBe(1.0);
    expect(triggerProgress("mouth_open", metrics({ mouthOpenRatio: 99.0 }), 0.35)).toBe(1.0);
    expect(triggerProgress("mouth_left", metrics({ mouthShiftRatio: 0.5 }), 0.05)).toBe(0.0);
  });

  it("only fills the both-eyes bar during a two-eye blink", () => {
    const closed = metrics({ earA: 0.1, earB: 0.1 });
    expect(triggerProgress("blink_a", closed, 0.21)).toBe(0.0);
    expect(triggerProgress("blink_b", closed, 0.21)).toBe(0.0);
    expect(triggerProgress("blink_both", closed, 0.21)).toBeCloseTo(1.0);
  });
});
