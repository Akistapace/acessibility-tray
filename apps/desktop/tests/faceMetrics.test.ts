import { describe, expect, it } from "vitest";
import { computeFaceMetrics, type Point } from "../src/renderer/tracking/faceMetrics";

// Build a 468-point landmark array (MediaPipe FaceMesh topology) with every
// index defaulted to the origin, then override only the indices this
// module reads. Coordinates are picked to make the expected ratios easy to
// hand-verify, not to resemble a real face.
function landmarks(overrides: Record<number, Point>): Point[] {
  const pts: Point[] = Array.from({ length: 468 }, () => [0, 0]);
  for (const [index, point] of Object.entries(overrides)) {
    pts[Number(index)] = point;
  }
  return pts;
}

describe("computeFaceMetrics", () => {
  it("returns null for an empty landmark list", () => {
    expect(computeFaceMetrics([])).toBeNull();
  });

  it("computes a symmetric eye-aspect-ratio for a level, evenly-spaced eye", () => {
    // EYE_A = [33, 160, 158, 133, 153, 144] -- corners at 33/133, lids at
    // 160/158 (top) and 153/144 (bottom), 1 unit above/below the midline.
    const pts = landmarks({
      33: [0, 0], 133: [10, 0],
      160: [3, -1], 158: [7, -1],
      153: [3, 1], 144: [7, 1],
      362: [0, 0], 263: [10, 0], 385: [3, -1], 387: [7, -1], 373: [3, 1], 380: [7, 1],
      1: [5, 5], 10: [5, -5], 152: [5, 15],
      168: [5, -2], 61: [2, 8], 291: [8, 8], 13: [5, 6], 14: [5, 10],
      105: [2, -3], 334: [8, -3], 159: [2, 0], 386: [8, 0],
    });
    const metrics = computeFaceMetrics(pts)!;
    // vertical = dist(160,144) + dist(158,153); horizontal = 2*dist(33,133)
    expect(metrics.earA).toBeGreaterThan(0);
    expect(metrics.earA).toBeCloseTo(metrics.earB, 5); // symmetric setup -> equal EAR
  });

  it("computes mouth_open_ratio as vertical-over-horizontal mouth distance", () => {
    const pts = landmarks({
      33: [0, 0], 133: [10, 0], 160: [3, -1], 158: [7, -1], 153: [3, 1], 144: [7, 1],
      362: [0, 0], 263: [10, 0], 385: [3, -1], 387: [7, -1], 373: [3, 1], 380: [7, 1],
      1: [5, 5], 10: [5, -5], 152: [5, 15], 168: [5, -2],
      61: [0, 5], 291: [10, 5], // mouth corners, 10 apart
      13: [5, 3], 14: [5, 7],   // mouth top/bottom, 4 apart
      105: [2, -3], 334: [8, -3], 159: [2, 0], 386: [8, 0],
    });
    const metrics = computeFaceMetrics(pts)!;
    expect(metrics.mouthOpenRatio).toBeCloseTo(4 / 10, 5);
  });

  it("gives mouthShiftRatio the correct sign for a mouth shifted to the user's right", () => {
    const base = {
      33: [0, 0] as Point, 133: [10, 0] as Point, 160: [3, -1] as Point, 158: [7, -1] as Point,
      153: [3, 1] as Point, 144: [7, 1] as Point,
      362: [0, 0] as Point, 263: [10, 0] as Point, 385: [3, -1] as Point, 387: [7, -1] as Point,
      373: [3, 1] as Point, 380: [7, 1] as Point,
      1: [5, 5] as Point, 10: [5, -5] as Point, 152: [5, 15] as Point,
      168: [5, -2] as Point, // axis top, straight above chin (152) -> vertical axis
      13: [5, 6] as Point, 14: [5, 10] as Point,
      105: [2, -3] as Point, 334: [8, -3] as Point, 159: [2, 0] as Point, 386: [8, 0] as Point,
    };
    const shiftedRight = computeFaceMetrics(landmarks({ ...base, 61: [7, 8], 291: [13, 8] }))!;
    const shiftedLeft = computeFaceMetrics(landmarks({ ...base, 61: [-3, 8], 291: [3, 8] }))!;
    expect(shiftedRight.mouthShiftRatio).toBeGreaterThan(0);
    expect(shiftedLeft.mouthShiftRatio).toBeLessThan(0);
  });
});
