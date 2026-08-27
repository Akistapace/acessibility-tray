import { performance } from "node:perf_hooks";
import type { AppConfig } from "./config.service";
import { MOUTH_CLOSED_MAX, triggerProgress, type FaceMetrics } from "@facemesh-mouse/shared";

export { MOUTH_CLOSED_MAX, triggerProgress };

const REPEATING_ACTIONS = new Set(["scroll_up", "scroll_down"]);
const HOLD_ACTIONS = new Set(["left_drag"]);
const CONTINUOUS_ACTIONS = new Set([...HOLD_ACTIONS, ...REPEATING_ACTIONS]);

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

interface GestureState {
  metSince: number | null;
  firedThisHold: boolean;
  lastFiredAt: number;
  releasePendingSince: number | null;
}

function freshState(): GestureState {
  return { metSince: null, firedThisHold: false, lastFiredAt: -1e9, releasePendingSince: null };
}

export class GestureEngine {
  private config: AppConfig;
  private readonly clock: () => number;
  private state = new Map<string, GestureState>();
  lastReleased: string[] = [];

  constructor(config: AppConfig, clock: () => number = () => performance.now() / 1000) {
    this.config = config;
    this.clock = clock;
    for (const name of Object.keys(config.gestures)) this.state.set(name, freshState());
  }

  updateConfig(config: AppConfig): void {
    this.config = config;
    for (const name of Object.keys(config.gestures)) {
      if (!this.state.has(name)) this.state.set(name, freshState());
    }
  }

  evaluate(metrics: FaceMetrics): string[] {
    const fired: string[] = [];
    const released: string[] = [];
    const now = this.clock();

    for (const [name, gestureCfg] of Object.entries(this.config.gestures)) {
      const state = this.state.get(name)!;
      const continuous = CONTINUOUS_ACTIONS.has(gestureCfg.action);

      if (!condition(name, metrics, gestureCfg.threshold)) {
        if (state.firedThisHold && continuous) {
          if (state.releasePendingSince === null) {
            state.releasePendingSince = now;
          } else if ((now - state.releasePendingSince) * 1000.0 >= gestureCfg.hold_ms) {
            if (HOLD_ACTIONS.has(gestureCfg.action)) released.push(name);
            state.metSince = null;
            state.firedThisHold = false;
            state.releasePendingSince = null;
          }
          continue;
        }
        state.metSince = null;
        state.firedThisHold = false;
        state.releasePendingSince = null;
        continue;
      }

      state.releasePendingSince = null;
      if (state.metSince === null) state.metSince = now;

      if (state.firedThisHold) {
        if (REPEATING_ACTIONS.has(gestureCfg.action) && (now - state.lastFiredAt) * 1000.0 >= gestureCfg.cooldown_ms) {
          fired.push(name);
          state.lastFiredAt = now;
        }
        continue;
      }

      if ((now - state.metSince) * 1000.0 < gestureCfg.hold_ms) continue;

      if ((now - state.lastFiredAt) * 1000.0 >= gestureCfg.cooldown_ms) {
        fired.push(name);
        state.lastFiredAt = now;
        state.firedThisHold = true;
      }
    }

    this.lastReleased = released;
    return fired;
  }
}
