import { describe, expect, it } from "vitest";
import { WIDTH, WINDOW_HEIGHT, MARGIN, defaultPosition, resolvePosition } from "../src/main/windows/buttonsPosition";

describe("defaultPosition", () => {
  it("insets from the bottom-right corner", () => {
    expect(defaultPosition(1000, 800)).toEqual({
      x: 1000 - WIDTH - MARGIN,
      y: 800 - WINDOW_HEIGHT - MARGIN,
    });
  });

  it("sits above a reserved taskbar", () => {
    expect(defaultPosition(1000, 800, 48)).toEqual({
      x: 1000 - WIDTH - MARGIN,
      y: 800 - WINDOW_HEIGHT - MARGIN - 48,
    });
  });
});

describe("resolvePosition", () => {
  it("uses the saved spot when it still fits", () => {
    expect(resolvePosition(50, 60, 1000, 800)).toEqual({ x: 50, y: 60 });
  });

  it("falls back to default without a saved spot", () => {
    expect(resolvePosition(null, null, 1000, 800)).toEqual(defaultPosition(1000, 800));
  });

  it("falls back when the saved spot is off a smaller screen", () => {
    expect(resolvePosition(1900, 1000, 1000, 800)).toEqual(defaultPosition(1000, 800));
  });

  it("accepts the saved spot exactly at the far edge", () => {
    const edgeX = 1000 - WIDTH;
    const edgeY = 800 - WINDOW_HEIGHT;
    expect(resolvePosition(edgeX, edgeY, 1000, 800)).toEqual({ x: edgeX, y: edgeY });
  });
});
