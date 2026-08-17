export function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

const ACCELERATION_REFERENCE = 0.05;

export function accelerate(delta: number, acceleration: number, reference = ACCELERATION_REFERENCE): number {
  const magnitude = Math.abs(delta);
  if (magnitude < 1e-9) return 0.0;
  const gain = Math.pow(magnitude / reference, acceleration);
  return delta * gain;
}
