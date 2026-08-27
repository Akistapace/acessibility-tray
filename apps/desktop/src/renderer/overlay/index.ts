import { pulseRadius, RING_COLOR, START_RADIUS, END_RADIUS, DURATION_MS } from "./pulse.js";

const canvas = document.getElementById("canvas") as HTMLCanvasElement;
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;
const ctx = canvas.getContext("2d")!;

// Incoming x/y coordinates are DIP/logical virtual-desktop pixels (main
// process converts nut-js's physical-pixel position before sending, see
// main/index.ts). This window's canvas origin (0, 0) corresponds to the
// window's own screen position -- (window.screenX, window.screenY) -- which
// is (minX, minY) of the display union computed in overlayWindow.ts, not
// (0, 0). Translate before drawing.
function toLocal(x: number, y: number): { x: number; y: number } {
  return { x: x - window.screenX, y: y - window.screenY };
}

function drawPulse(x: number, y: number, color: string): void {
  const steps = 10;
  let index = 0;
  const timer = setInterval(() => {
    ctx.clearRect(x - END_RADIUS - 4, y - END_RADIUS - 4, (END_RADIUS + 4) * 2, (END_RADIUS + 4) * 2);
    if (index > steps) {
      clearInterval(timer);
      return;
    }
    const radius = pulseRadius(index / steps, START_RADIUS, END_RADIUS);
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.stroke();
    index += 1;
  }, DURATION_MS / steps);
}

window.backend.on("action", (message) => {
  const action = message as { x: number; y: number };
  const { x, y } = toLocal(action.x, action.y);
  drawPulse(x, y, RING_COLOR);
});

window.backend.on("keyboard_result", (message) => {
  const result = message as { x: number; y: number };
  const { x, y } = toLocal(result.x, result.y);
  drawPulse(x, y, RING_COLOR);
});
