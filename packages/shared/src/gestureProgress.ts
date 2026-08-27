import type { FaceMetrics } from "./types/tracking";

export const MOUTH_CLOSED_MAX = 0.15;

const FIRES_BELOW = new Set(["blink_a", "blink_b", "blink_both"]);

function condition(name: string, m: FaceMetrics, threshold: number): boolean {
  switch (name) {
    case "blink_a": return m.earA < threshold && m.earB >= threshold;
    case "blink_b": return m.earB < threshold && m.earA >= threshold;
    case "blink_both": return m.earA < threshold && m.earB < threshold;
    case "eyebrow_a": return m.eyebrowRaiseA > threshold && m.eyebrowRaiseB <= threshold;
    case "eyebrow_b": return m.eyebrowRaiseB > threshold && m.eyebrowRaiseA <= threshold;
    case "eyebrow_both": return m.eyebrowRaiseA > threshold && m.eyebrowRaiseB > threshold;
    case "mouth_open": return m.mouthOpenRatio > threshold;
    case "mouth_left": return m.mouthShiftRatio < -threshold && m.mouthOpenRatio <= MOUTH_CLOSED_MAX;
    case "mouth_right": return m.mouthShiftRatio > threshold && m.mouthOpenRatio <= MOUTH_CLOSED_MAX;
    default: throw new Error(`Unknown gesture: ${name}`);
  }
}

function progressValue(name: string, m: FaceMetrics): number {
  switch (name) {
    case "blink_a": return m.earA;
    case "blink_b": return m.earB;
    case "blink_both": return Math.max(m.earA, m.earB);
    case "eyebrow_a": return m.eyebrowRaiseA;
    case "eyebrow_b": return m.eyebrowRaiseB;
    case "eyebrow_both": return Math.min(m.eyebrowRaiseA, m.eyebrowRaiseB);
    case "mouth_open": return m.mouthOpenRatio;
    case "mouth_left": return -m.mouthShiftRatio;
    case "mouth_right": return m.mouthShiftRatio;
    default: throw new Error(`Unknown gesture: ${name}`);
  }
}

function isReachable(name: string, m: FaceMetrics, threshold: number): boolean {
  switch (name) {
    case "blink_a": return m.earB >= threshold;
    case "blink_b": return m.earA >= threshold;
    case "eyebrow_a": return m.eyebrowRaiseB <= threshold;
    case "eyebrow_b": return m.eyebrowRaiseA <= threshold;
    case "mouth_left":
    case "mouth_right": return m.mouthOpenRatio <= MOUTH_CLOSED_MAX;
    default: return true;
  }
}

// Shared by main (gesture-trigger evaluation) and the tracking renderer
// (camera-preview highlight color) so both sides read the same 0..1
// "how close is this gesture to firing" value off the same metrics.
export function triggerProgress(name: string, metrics: FaceMetrics, threshold: number): number {
  if (!isReachable(name, metrics, threshold)) return 0.0;
  const value = progressValue(name, metrics);
  const t = threshold || 1e-6;
  const ratio = FIRES_BELOW.has(name) ? t / Math.max(value, 1e-6) : value / t;
  return Math.max(0.0, Math.min(1.0, ratio));
}
