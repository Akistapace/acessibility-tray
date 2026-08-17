import { describe, expect, it } from "vitest";
import { pulseRadius } from "../src/ui/overlay/pulse";

describe("pulseRadius", () => {
  it("starts at the start radius", () => {
    expect(pulseRadius(0, 6, 28)).toBe(6);
  });

  it("ends at the end radius", () => {
    expect(pulseRadius(1, 6, 28)).toBe(28);
  });

  it("interpolates linearly at the midpoint", () => {
    expect(pulseRadius(0.5, 6, 28)).toBe(17);
  });
});
