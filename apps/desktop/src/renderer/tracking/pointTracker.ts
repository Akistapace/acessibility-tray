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
