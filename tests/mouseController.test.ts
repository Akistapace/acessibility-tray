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
