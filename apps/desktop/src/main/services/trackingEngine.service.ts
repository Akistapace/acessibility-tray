import { GestureEngine } from "./gestures.service";
import { MouseController, type MouseDriver } from "./mouseController.service";
import type { AppConfig } from "./config.service";
import type { FaceMetrics, TrackingFrame } from "@facemesh-mouse/shared";

export class TrackingEngine {
  controlEnabled = false;
  paused = false;
  noFace = false;
  private wasActive = false;
  private gestureEngine: GestureEngine;
  readonly mouseController: MouseController;

  constructor(
    config: AppConfig,
    driver: MouseDriver,
    screenSize: [number, number],
    onAction?: (gesture: string, action: string, position: [number, number]) => void
  ) {
    this.gestureEngine = new GestureEngine(config);
    this.mouseController = new MouseController(config, screenSize, driver, undefined, onAction);
  }

  get yielded(): boolean {
    return this.mouseController.yielded;
  }

  // Mirrors Python's Engine.stop(), called from main()'s finally block:
  // releases any held mouse button (e.g. a left_drag in progress) so quitting
  // mid-drag doesn't leave the physical button held down system-wide.
  async stop(): Promise<void> {
    await this.mouseController.releaseAllHolds();
  }

  updateConfig(config: AppConfig): void {
    this.gestureEngine.updateConfig(config);
    this.mouseController.updateConfig(config);
  }

  async onFrame(frame: TrackingFrame): Promise<void> {
    if (frame.metrics === null) {
      this.noFace = true;
      if (this.wasActive) await this.mouseController.releaseAllHolds();
      this.wasActive = false;
      return;
    }
    this.noFace = false;
    await this.driveControl(frame.metrics, frame.movement);
  }

  private async driveControl(metrics: FaceMetrics, movement: [number, number]): Promise<void> {
    const activeNow = this.controlEnabled && !this.paused;
    if (activeNow) {
      if (!this.wasActive) await this.mouseController.reanchor();
      await this.mouseController.moveCursor(movement[0], movement[1]);
      if (!this.mouseController.frozen) await this.mouseController.evaluateDwell();
      for (const gestureName of this.gestureEngine.evaluate(metrics)) {
        await this.mouseController.fireAction(gestureName);
      }
      for (const gestureName of this.gestureEngine.lastReleased) {
        await this.mouseController.releaseAction(gestureName);
      }
    } else if (this.wasActive) {
      await this.mouseController.releaseAllHolds();
    }
    this.wasActive = activeNow;
  }
}
