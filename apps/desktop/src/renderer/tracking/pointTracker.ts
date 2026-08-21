// Type-only: @techstark/opencv-js's default export is a Promise<CV> at
// runtime (the WASM module isn't ready synchronously on import), so this
// file must never touch it as a value at module scope -- that crashes on
// import (see task-15-report.md). PointTracker instead receives the already
// -resolved `cv` namespace via constructor injection from index.ts, which
// awaits it once. `typeof import(...)` is a pure type query (no runtime
// import emitted); a plain `import type CvNamespace from "..."` default
// import doesn't work here because this package has no `export default` in
// its .d.ts, so TS resolves the synthetic default to a *namespace*, and
// namespaces can't be used as ordinary type annotations (TS2709).
type CvNamespace = typeof import("@techstark/opencv-js");
import type { Mat as CvMat } from "@techstark/opencv-js";

export const PRUNING_CELL_FRACTION = 0.02;
export const MIN_ADD_DISTANCE_FRACTION = 0.03;
export const FACE_ASPECT_RATIO = 1.3;

export type Point = [number, number];

export function prunePoints(
  points: Point[],
  prevPoints: Point[],
  status: number[],
  nose: Point,
  headSize: number
): { points: Point[]; prevPoints: Point[] } {
  const keptIdx: number[] = [];
  status.forEach((s, i) => { if (s === 1) keptIdx.push(i); });
  let curr = keptIdx.map((i) => points[i]);
  let prev = keptIdx.map((i) => prevPoints[i]);

  const cell = Math.max(headSize * PRUNING_CELL_FRACTION, 1.0);
  const seenCells = new Map<string, number>();
  curr.forEach(([x, y], index) => {
    seenCells.set(`${Math.floor(x / cell)}:${Math.floor(y / cell)}`, index);
  });
  if (seenCells.size) {
    const unique = Array.from(seenCells.values()).sort((a, b) => a - b);
    curr = unique.map((i) => curr[i]);
    prev = unique.map((i) => prev[i]);
  }

  if (curr.length) {
    const [noseX, noseY] = nose;
    const keep: number[] = [];
    curr.forEach(([x, y], index) => {
      const distance = Math.hypot((x - noseX) * FACE_ASPECT_RATIO, y - noseY);
      if (distance <= headSize) keep.push(index);
    });
    curr = keep.map((i) => curr[i]);
    prev = keep.map((i) => prev[i]);
  }

  return { points: curr, prevPoints: prev };
}

export function shouldAddPoint(candidate: Point, points: Point[], headSize: number): boolean {
  if (!points.length) return true;
  const minDistance = Math.max(headSize * MIN_ADD_DISTANCE_FRACTION, 1.0);
  return !points.some(
    ([x, y]) => Math.abs(x - candidate[0]) <= minDistance && Math.abs(y - candidate[1]) <= minDistance
  );
}

export function meanMovement(points: Point[], prevPoints: Point[]): [number, number] {
  if (!points.length) return [0.0, 0.0];
  let sumX = 0, sumY = 0;
  for (let i = 0; i < points.length; i++) {
    sumX += points[i][0] - prevPoints[i][0];
    sumY += points[i][1] - prevPoints[i][1];
  }
  return [sumX / points.length, sumY / points.length];
}

// These two don't depend on cv at all, so (unlike LK_WIN_SIZE/LK_CRITERIA
// below) they stay as plain module-scope constants.
const LK_MAX_LEVEL = 2;
const LK_MIN_EIG_THRESHOLD = 0.001;

function toMat(cv: CvNamespace, points: Point[]): CvMat {
  const mat = new cv.Mat(points.length, 1, cv.CV_32FC2);
  for (let i = 0; i < points.length; i++) {
    mat.data32F[i * 2] = points[i][0];
    mat.data32F[i * 2 + 1] = points[i][1];
  }
  return mat;
}

function fromMat(mat: CvMat): Point[] {
  const out: Point[] = [];
  for (let i = 0; i < mat.rows; i++) {
    out.push([mat.data32F[i * 2], mat.data32F[i * 2 + 1]]);
  }
  return out;
}

export class PointTracker {
  private readonly winSize: InstanceType<CvNamespace["Size"]>;
  private readonly criteria: InstanceType<CvNamespace["TermCriteria"]>;
  private prevGray: CvMat | null = null;
  private points: Point[] = [];
  private prevPoints: Point[] = [];
  private movement: [number, number] = [0, 0];

  constructor(private readonly cv: CvNamespace) {
    this.winSize = new cv.Size(21, 21);
    this.criteria = new cv.TermCriteria(cv.TermCriteria_EPS + cv.TermCriteria_COUNT, 30, 0.03);
  }

  get pointCount(): number {
    return this.points.length;
  }

  reset(): void {
    this.prevGray?.delete();
    this.prevGray = null;
    this.points = [];
    this.prevPoints = [];
    this.movement = [0, 0];
  }

  update(gray: CvMat, nose: Point, headSize: number, candidates: Point[]): void {
    const cv = this.cv;
    if (this.prevGray && this.points.length) {
      const prevPtsMat = toMat(cv, this.points);
      const nextPtsMat = new cv.Mat();
      const status = new cv.Mat();
      const err = new cv.Mat();
      cv.calcOpticalFlowPyrLK(
        this.prevGray, gray, prevPtsMat, nextPtsMat, status, err,
        this.winSize, LK_MAX_LEVEL, this.criteria, 0, LK_MIN_EIG_THRESHOLD
      );

      const statusArr = Array.from(status.data);
      const { points, prevPoints } = prunePoints(fromMat(nextPtsMat), this.points, statusArr, nose, headSize);
      this.points = points;
      this.prevPoints = prevPoints;

      prevPtsMat.delete();
      nextPtsMat.delete();
      status.delete();
      err.delete();
    } else {
      this.prevPoints = [...this.points];
    }

    this.movement = meanMovement(this.points, this.prevPoints);

    for (const candidate of candidates) {
      if (shouldAddPoint(candidate, this.points, headSize)) {
        this.points = [...this.points, candidate];
        this.prevPoints = [...this.prevPoints, candidate];
      }
    }

    this.prevGray?.delete();
    this.prevGray = gray.clone();
  }

  getMovement(): [number, number] {
    return this.movement;
  }
}
