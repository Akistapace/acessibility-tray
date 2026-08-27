// Same expanding-ring interpolation as click_feedback.py's show_pulse:
// radius grows linearly from startRadius to endRadius as progress goes
// from 0 to 1.
export function pulseRadius(progress: number, startRadius: number, endRadius: number): number {
  return startRadius + (endRadius - startRadius) * progress;
}

export const RING_COLOR = "#4da3ff";
export const START_RADIUS = 6;
export const END_RADIUS = 28;
export const DURATION_MS = 300;
