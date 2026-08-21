export const SIZE = 60;
export const GAP = 6;
export const MARGIN = 24;
// Breathing room around the circle pair, inside the window: the whole
// window is one hoverable "container" (see buttons/index.html's
// body:hover), so this is what makes the drag handle appear as soon as the
// cursor gets close to the buttons, not only once it lands exactly on a
// circle -- important with a head-tracked cursor, which isn't pixel-precise.
export const PADDING = 10;
export const WIDTH = SIZE * 2 + GAP + PADDING * 2;
// A slim strip above the two circles for the drag handle (see
// buttons/index.html) -- kept out of SIZE so the circles' own hit area
// stays exactly their visual size.
export const HANDLE_HEIGHT = 22;
export const WINDOW_HEIGHT = SIZE + HANDLE_HEIGHT + PADDING;

export interface Point {
  x: number;
  y: number;
}

export function defaultPosition(screenW: number, screenH: number, taskbarReservedPx = 0): Point {
  return { x: screenW - WIDTH - MARGIN, y: screenH - WINDOW_HEIGHT - MARGIN - taskbarReservedPx };
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
  if (
    !(savedX >= 0 && savedX <= screenW - WIDTH) ||
    !(savedY >= 0 && savedY <= screenH - WINDOW_HEIGHT)
  ) {
    return defaultPosition(screenW, screenH, taskbarReservedPx);
  }
  return { x: savedX, y: savedY };
}
