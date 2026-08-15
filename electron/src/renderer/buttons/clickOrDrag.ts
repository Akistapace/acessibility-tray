export const CLICK_DRAG_THRESHOLD_PX = 5;

export interface Point {
  x: number;
  y: number;
}

export function isClick(press: Point, release: Point): boolean {
  return (
    Math.abs(release.x - press.x) <= CLICK_DRAG_THRESHOLD_PX &&
    Math.abs(release.y - press.y) <= CLICK_DRAG_THRESHOLD_PX
  );
}
