export const SIZE = 60;
export const GAP = 6;
export const WIDTH = SIZE * 2 + GAP;
export const MARGIN = 24;

export interface Point {
  x: number;
  y: number;
}

export function defaultPosition(screenW: number, screenH: number, taskbarReservedPx = 0): Point {
  return { x: screenW - WIDTH - MARGIN, y: screenH - SIZE - MARGIN - taskbarReservedPx };
}

export function resolvePosition(
  savedX: number | null,
  savedY: number | null,
  screenW: number,
  screenH: number,
  taskbarReservedPx = 0
): Point {
  if (savedX === null || savedY === null) {
    return defaultPosition(screenW, screenH, taskbarReservedPx);
  }
  if (!(savedX >= 0 && savedX <= screenW - WIDTH) || !(savedY >= 0 && savedY <= screenH - SIZE)) {
    return defaultPosition(screenW, screenH, taskbarReservedPx);
  }
  return { x: savedX, y: savedY };
}
