import { pulseRadius, RING_COLOR, WARNING_COLOR, START_RADIUS, END_RADIUS, DURATION_MS } from "./pulse.js";

declare global {
  interface Window {
    backend: {
      send: (message: Record<string, unknown>) => void;
      on: (channel: string, callback: (message: unknown) => void) => () => void;
    };
  }
}

const canvas = document.getElementById("canvas") as HTMLCanvasElement;
canvas.width = window.screen.width;
canvas.height = window.screen.height;
const ctx = canvas.getContext("2d")!;
const tooltip = document.getElementById("tooltip") as HTMLDivElement;

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
  drawPulse(action.x, action.y, RING_COLOR);
});

window.backend.on("keyboard_result", (message) => {
  const result = message as { opened: boolean; x: number; y: number };
  if (result.opened) {
    drawPulse(result.x, result.y, RING_COLOR);
  } else {
    drawPulse(result.x, result.y, WARNING_COLOR);
    showTooltip(result.x, result.y, "Clique num campo de texto antes de abrir o teclado");
  }
});
