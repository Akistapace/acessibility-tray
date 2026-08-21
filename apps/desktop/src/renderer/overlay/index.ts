import { pulseRadius, RING_COLOR, WARNING_COLOR, START_RADIUS, END_RADIUS, DURATION_MS } from "./pulse.js";

const canvas = document.getElementById("canvas") as HTMLCanvasElement;
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;
const ctx = canvas.getContext("2d")!;
const tooltip = document.getElementById("tooltip") as HTMLDivElement;

// Incoming x/y coordinates are absolute virtual-desktop pixels (from
// pynput on the Python side). This window's canvas origin (0, 0)
// corresponds to the window's own screen position -- (window.screenX,
// window.screenY) -- which is (minX, minY) of the display union computed
// in overlayWindow.ts, not (0, 0). Translate before drawing.
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

function showTooltip(x: number, y: number, text: string): void {
  tooltip.textContent = text;
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y - 40}px`;
  tooltip.style.display = "block";
  setTimeout(() => (tooltip.style.display = "none"), 2500);
}

window.backend.on("action", (message) => {
  const action = message as { x: number; y: number };
  const { x, y } = toLocal(action.x, action.y);
  drawPulse(x, y, RING_COLOR);
});

window.backend.on("keyboard_result", (message) => {
  const result = message as { opened: boolean; x: number; y: number };
  const { x, y } = toLocal(result.x, result.y);
  if (result.opened) {
    drawPulse(x, y, RING_COLOR);
  } else {
    drawPulse(x, y, WARNING_COLOR);
    showTooltip(x, y, "Clique num campo de texto antes de abrir o teclado");
  }
});
