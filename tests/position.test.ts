import { describe, expect, it } from "vitest";
import { CLICK_DRAG_THRESHOLD_PX, isClick } from "../src/ui/buttons/clickOrDrag";
import { WIDTH, SIZE, MARGIN, defaultPosition, resolvePosition } from "../src/modules/windows/buttonsPosition";

describe("isClick", () => {
  it("is a click within the threshold on both axes", () => {
    expect(isClick({ x: 100, y: 100 }, { x: 103, y: 102 })).toBe(true);
  });

  it("is a click exactly at the threshold", () => {
    const t = CLICK_DRAG_THRESHOLD_PX;
    expect(isClick({ x: 100, y: 100 }, { x: 100 + t, y: 100 - t })).toBe(true);
  });

  it("is a drag past the threshold on either axis", () => {
    const t = CLICK_DRAG_THRESHOLD_PX;
    expect(isClick({ x: 100, y: 100 }, { x: 100 + t + 1, y: 100 })).toBe(false);
    expect(isClick({ x: 100, y: 100 }, { x: 100, y: 100 + t + 1 })).toBe(false);
  });
});

describe("defaultPosition", () => {
  it("insets from the bottom-right corner", () => {
    expect(defaultPosition(1000, 800)).toEqual({ x: 1000 - WIDTH - MARGIN, y: 800 - SIZE - MARGIN });
  });

  it("sits above a reserved taskbar", () => {
    expect(defaultPosition(1000, 800, 48)).toEqual({
      x: 1000 - WIDTH - MARGIN,
      y: 800 - SIZE - MARGIN - 48,
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
    const edgeY = 800 - SIZE;
    expect(resolvePosition(edgeX, edgeY, 1000, 800)).toEqual({ x: edgeX, y: edgeY });
  });
});
