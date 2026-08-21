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

import { performance } from "node:perf_hooks";
import type { AppConfig } from "./config.service";

export interface MouseDriver {
  getPosition(): Promise<[number, number]>;
  setPosition(pos: [number, number]): Promise<void>;
  click(button: "left" | "right", count: 1 | 2): Promise<void>;
  pressButton(button: "left"): Promise<void>;
  releaseButton(button: "left"): Promise<void>;
  scroll(dx: number, dy: number): Promise<void>;
}

export class NutJsMouseDriver implements MouseDriver {
  // nut-js defaults to a 100ms artificial delay before every click/press/
  // release/scroll call, meant to humanize input for automation use cases.
  // We fire actions from discrete gesture events, not simulated human input,
  // and this delay was fully serialized with tracking-frame processing
  // (main.onTrackingFrame drops any frame that arrives while one is still in
  // flight), so every click/scroll stalled cursor movement for ~100ms.
  private nut = import("@nut-tree-fork/nut-js").then((mod) => {
    mod.mouse.config.autoDelayMs = 0;
    return mod;
  });

  // nut-js's own screen size (backed by the same native libnut binding that
  // setPosition/getPosition use) reports hardware pixel resolution, unlike
  // Electron's screen module which reports DPI-scaled logical pixels. The
  // cursor clamp bound must match setPosition's coordinate space, or the
  // cursor can never reach the true edge on any display above 100% scaling.
  async getScreenSize(): Promise<[number, number]> {
    const { screen } = await this.nut;
    return [await screen.width(), await screen.height()];
  }

  async getPosition(): Promise<[number, number]> {
    const { mouse } = await this.nut;
    const pos = await mouse.getPosition();
    return [pos.x, pos.y];
  }
  async setPosition(pos: [number, number]): Promise<void> {
    const { mouse, Point } = await this.nut;
    await mouse.setPosition(new Point(pos[0], pos[1]));
  }
  async click(button: "left" | "right", count: 1 | 2): Promise<void> {
    const { mouse, Button } = await this.nut;
    const btn = button === "left" ? Button.LEFT : Button.RIGHT;
    if (count === 1) await mouse.click(btn);
    else await mouse.doubleClick(btn);
  }
  async pressButton(button: "left"): Promise<void> {
    const { mouse, Button } = await this.nut;
    await mouse.pressButton(button === "left" ? Button.LEFT : Button.RIGHT);
  }
  async releaseButton(button: "left"): Promise<void> {
    const { mouse, Button } = await this.nut;
    await mouse.releaseButton(button === "left" ? Button.LEFT : Button.RIGHT);
  }
  async scroll(dx: number, dy: number): Promise<void> {
    const { mouse } = await this.nut;
    if (dy > 0) await mouse.scrollUp(Math.abs(dy));
    else if (dy < 0) await mouse.scrollDown(Math.abs(dy));
    if (dx > 0) await mouse.scrollRight(Math.abs(dx));
    else if (dx < 0) await mouse.scrollLeft(Math.abs(dx));
  }
}

const ACTIONS: Record<string, (driver: MouseDriver) => Promise<void>> = {
  left_click: (d) => d.click("left", 1),
  right_click: (d) => d.click("right", 1),
  double_click: (d) => d.click("left", 2),
  scroll_up: (d) => d.scroll(0, 1),
  scroll_down: (d) => d.scroll(0, -1),
  none: async () => {},
};

const YIELD_DETECT_PX = 2;
const DWELL_STILL_PX = 3;

export class MouseController {
  private config: AppConfig;
  private readonly screenW: number;
  private readonly screenH: number;
  private readonly driver: MouseDriver;
  private readonly clock: () => number;
  private readonly onAction?: (gesture: string, action: string, position: [number, number]) => void;

  private cursorX: number | null = null;
  private cursorY: number | null = null;
  yielded = false;
  private yieldStartedAt: number | null = null;
  private lastSeenX: number | null = null;
  private lastSeenY: number | null = null;
  private dwellAnchorX: number | null = null;
  private dwellAnchorY: number | null = null;
  private dwellStartedAt: number | null = null;
  private dwellFired = false;
  private dragPressed = false;
  frozen = false;

  constructor(
    config: AppConfig,
    screenSize: [number, number],
    driver: MouseDriver,
    clock: () => number = () => performance.now() / 1000,
    onAction?: (gesture: string, action: string, position: [number, number]) => void
  ) {
    this.config = config;
    [this.screenW, this.screenH] = screenSize;
    this.driver = driver;
    this.clock = clock;
    this.onAction = onAction;
  }

  updateConfig(config: AppConfig): void {
    this.config = config;
  }

  async reanchor(): Promise<void> {
    const [x, y] = await this.driver.getPosition();
    this.cursorX = x;
    this.cursorY = y;
    this.lastSeenX = x;
    this.lastSeenY = y;
    this.yielded = false;
    this.yieldStartedAt = null;
    this.dwellAnchorX = null;
    this.dwellAnchorY = null;
    this.dwellFired = false;
  }

  async moveCursor(movementX: number, movementY: number): Promise<void> {
    if (this.cursorX === null || this.cursorY === null) return;
    if (this.frozen) return;

    const [curX, curY] = await this.driver.getPosition();

    if (this.yielded) {
      await this.updateYieldTimer(curX, curY);
      return;
    }

    if (Math.abs(curX - this.cursorX) > YIELD_DETECT_PX || Math.abs(curY - this.cursorY) > YIELD_DETECT_PX) {
      this.yielded = true;
      this.yieldStartedAt = this.clock();
      this.lastSeenX = curX;
      this.lastSeenY = curY;
      return;
    }

    if (!Number.isFinite(movementX) || !Number.isFinite(movementY)) return;

    const cal = this.config.calibration;
    let deltaX = accelerate(movementX * cal.sensitivity_x, cal.acceleration);
    let deltaY = accelerate(movementY * cal.sensitivity_y, cal.acceleration);

    if (Math.abs(deltaX * this.screenW) < cal.motion_threshold_px) deltaX = 0.0;
    if (Math.abs(deltaY * this.screenH) < cal.motion_threshold_px) deltaY = 0.0;

    this.cursorX = clamp(this.cursorX + deltaX * this.screenW, 0, this.screenW - 1);
    this.cursorY = clamp(this.cursorY + deltaY * this.screenH, 0, this.screenH - 1);
    await this.driver.setPosition([Math.trunc(this.cursorX), Math.trunc(this.cursorY)]);
  }

  async evaluateDwell(): Promise<void> {
    const cal = this.config.calibration;
    if (!cal.dwell_click_enabled) {
      this.dwellAnchorX = null;
      this.dwellAnchorY = null;
      this.dwellFired = false;
      return;
    }

    const [curX, curY] = await this.driver.getPosition();

    if (
      this.dwellAnchorX === null ||
      Math.abs(curX - this.dwellAnchorX) > DWELL_STILL_PX ||
      Math.abs(curY - (this.dwellAnchorY as number)) > DWELL_STILL_PX
    ) {
      this.dwellAnchorX = curX;
      this.dwellAnchorY = curY;
      this.dwellStartedAt = this.clock();
      this.dwellFired = false;
      return;
    }

    if (this.dwellFired) return;

    if (this.clock() - (this.dwellStartedAt as number) >= cal.dwell_time_s) {
      if (this.onAction) {
        try {
          this.onAction("dwell", "left_click", [curX, curY]);
        } catch (exc) {
          console.error(`facemesh-mouse: on_action failed (${exc})`);
        }
      }
      await ACTIONS.left_click(this.driver);
      this.dwellFired = true;
    }
  }

  private async updateYieldTimer(curX: number, curY: number): Promise<void> {
    if (
      Math.abs(curX - (this.lastSeenX as number)) > YIELD_DETECT_PX ||
      Math.abs(curY - (this.lastSeenY as number)) > YIELD_DETECT_PX
    ) {
      this.yieldStartedAt = this.clock();
    }
    this.lastSeenX = curX;
    this.lastSeenY = curY;

    const quietFor = this.clock() - (this.yieldStartedAt as number);
    if (quietFor >= this.config.calibration.yield_resume_after_s) {
      await this.reanchor();
    }
  }

  async fireAction(gestureName: string): Promise<void> {
    const action = this.config.gestures[gestureName].action;
    if (action !== "none" && this.onAction) {
      try {
        const position = await this.driver.getPosition();
        this.onAction(gestureName, action, position);
      } catch (exc) {
        console.error(`facemesh-mouse: on_action failed (${exc})`);
      }
    }
    if (action === "left_drag") {
      await this.driver.pressButton("left");
      this.dragPressed = true;
      return;
    }
    if (action === "freeze_cursor") {
      this.frozen = !this.frozen;
      return;
    }
    await ACTIONS[action](this.driver);
  }

  async releaseAction(gestureName: string): Promise<void> {
    const action = this.config.gestures[gestureName].action;
    if (action === "left_drag" && this.dragPressed) {
      await this.driver.releaseButton("left");
      this.dragPressed = false;
    }
  }

  async releaseAllHolds(): Promise<void> {
    if (this.dragPressed) {
      await this.driver.releaseButton("left");
      this.dragPressed = false;
    }
    this.frozen = false;
  }
}
