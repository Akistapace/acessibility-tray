// Key size/gap here must match renderer/keyboard/style.css's .key width and
// #keys gap -- there's no shared build-time constant between main and
// renderer CSS, so keep these two in sync by hand.
export const KEY_SIZE = 44;
export const KEY_GAP = 6;
export const PADDING = 12;
export const HANDLE_HEIGHT = 26;
export const MARGIN = 24;

// Widest row is the 12-key accent row (Á Ã Â À É Ê Í Ó Ô Õ Ú Ç), wider than
// either the 10-key letter/number rows -- that sets the window width.
const WIDEST_ROW_KEYS = 12;
export const WIDTH = KEY_SIZE * WIDEST_ROW_KEYS + KEY_GAP * (WIDEST_ROW_KEYS - 1) + PADDING * 2;

// "Full" mode is the tallest case: numbers row + punctuation row + 3 letter
// rows + accent row + bottom row = 7 rows. The window is sized for this
// once and never resized when toggling to compact (see design spec).
const FULL_MODE_ROW_COUNT = 7;
export const WINDOW_HEIGHT =
  HANDLE_HEIGHT + FULL_MODE_ROW_COUNT * KEY_SIZE + (FULL_MODE_ROW_COUNT - 1) * KEY_GAP + PADDING;

export interface Point {
  x: number;
  y: number;
}

export function defaultPosition(screenW: number, screenH: number, taskbarReservedPx = 0): Point {
  return { x: (screenW - WIDTH) / 2, y: screenH - WINDOW_HEIGHT - MARGIN - taskbarReservedPx };
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
