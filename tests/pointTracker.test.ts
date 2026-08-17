import { describe, expect, it } from "vitest";
import {
  FACE_ASPECT_RATIO,
  MIN_ADD_DISTANCE_FRACTION,
  PRUNING_CELL_FRACTION,
  meanMovement,
  prunePoints,
  shouldAddPoint,
  type Point,
} from "../src/modules/pointTracker";

describe("prunePoints", () => {
  it("drops points optical flow lost (status 0)", () => {
    const cur: Point[] = [[10, 10], [20, 20]];
    const prev: Point[] = [[9, 10], [19, 20]];
    const { points, prevPoints } = prunePoints(cur, prev, [1, 0], [15, 15], 100);
    expect(points).toEqual([[10, 10]]);
    expect(prevPoints).toEqual([[9, 10]]);
  });

  it("collapses points sharing a grid cell, keeping ones far enough apart", () => {
    const headSize = 250.0;
    const cell = headSize * PRUNING_CELL_FRACTION;
    const cur: Point[] = [[10, 10], [10 + cell * 0.4, 10 + cell * 0.4], [10 + cell * 6, 10 + cell * 6]];
    const { points } = prunePoints(cur, cur, [1, 1, 1], [20, 20], headSize);
    expect(points).toHaveLength(2);
  });

  it("scales grid deduplication with head size", () => {
    const cur: Point[] = [[10, 10], [14, 14]];
    const small = prunePoints(cur, cur, [1, 1], [0, 0], 100.0);
    const large = prunePoints(cur, cur, [1, 1], [0, 0], 1000.0);
    expect(small.points).toHaveLength(2);
    expect(large.points).toHaveLength(1);
  });

  it("culls points beyond the head ellipse", () => {
    const nose: Point = [100, 100];
    const cur: Point[] = [[110, 100], [400, 100]];
    const { points } = prunePoints(cur, cur, [1, 1], nose, 60);
    expect(points).toEqual([[110, 100]]);
  });

  it("stretches the cull ellipse horizontally by FACE_ASPECT_RATIO", () => {
    const nose: Point = [100, 100];
    const headSize = 60.0;
    const offset = 50.0; // 50 * 1.3 = 65 > 60 horizontally, 50 < 60 vertically
    expect(FACE_ASPECT_RATIO).toBe(1.3);

    const horizontal = prunePoints([[100 + offset, 100]], [[100 + offset, 100]], [1], nose, headSize);
    const vertical = prunePoints([[100, 100 + offset]], [[100, 100 + offset]], [1], nose, headSize);

    expect(horizontal.points).toHaveLength(0);
    expect(vertical.points).toHaveLength(1);
  });
});

describe("shouldAddPoint", () => {
  it("rejects a candidate near an existing point on both axes", () => {
    const headSize = 100.0;
    const minDistance = headSize * MIN_ADD_DISTANCE_FRACTION;
    const existing: Point[] = [[100, 100]];
    expect(shouldAddPoint([100 + minDistance - 1, 100 + minDistance - 1], existing, headSize)).toBe(false);
  });

  it("accepts a candidate clear on both axes", () => {
    const headSize = 100.0;
    const minDistance = headSize * MIN_ADD_DISTANCE_FRACTION;
    const existing: Point[] = [[100, 100]];
    expect(shouldAddPoint([100 + minDistance + 1, 100 + minDistance + 1], existing, headSize)).toBe(true);
  });

  it("accepts anything when there are no existing points", () => {
    expect(shouldAddPoint([5, 5], [], 100.0)).toBe(true);
  });

  it("accepts a candidate level but far horizontally (symmetric features)", () => {
    const existing: Point[] = [[100, 100]];
    expect(shouldAddPoint([160, 100], existing, 100.0)).toBe(true);
    expect(shouldAddPoint([100, 160], existing, 100.0)).toBe(true);
  });
});

describe("meanMovement", () => {
  it("averages movement across every point", () => {
    const cur: Point[] = [[10, 10], [20, 30]];
    const prev: Point[] = [[8, 9], [18, 26]];
    const [dx, dy] = meanMovement(cur, prev);
    expect(dx).toBeCloseTo(2.0);
    expect(dy).toBeCloseTo(2.5);
  });

  it("is zero without points", () => {
    expect(meanMovement([], [])).toEqual([0.0, 0.0]);
  });
});
