import fs from "node:fs";
import path from "node:path";

export const LOG_PATH = "clicks.log";

let enabled = false;
let currentPath = LOG_PATH;
let maxBytesLimit = 1_000_000;
let backupCountLimit = 3;

export function enable(logPath: string = LOG_PATH, maxBytes = 1_000_000, backupCount = 3): void {
  if (enabled) return;
  currentPath = logPath;
  maxBytesLimit = maxBytes;
  backupCountLimit = backupCount;
  enabled = true;
}

export function disable(): void {
  enabled = false;
}

function rotateIfNeeded(): void {
  let size = 0;
  try {
    size = fs.statSync(currentPath).size;
  } catch {
    return;
  }
  if (size < maxBytesLimit) return;

  for (let i = backupCountLimit - 1; i >= 1; i--) {
    const src = `${currentPath}.${i}`;
    const dest = `${currentPath}.${i + 1}`;
    if (fs.existsSync(src)) fs.renameSync(src, dest);
  }
  fs.renameSync(currentPath, `${currentPath}.1`);
}

function defaultWindowTitle(): string {
  // Real implementation wired in Task 8, step 4 -- placeholder title until
  // win32.ts exists so this module has no forward import to a file that
  // doesn't exist yet at this point in the plan.
  return "?";
}

export function record(
  gestureName: string,
  action: string,
  position: [number, number],
  windowTitleFn: () => string = defaultWindowTitle
): void {
  if (!enabled) return;
  const title = windowTitleFn() || "?";
  const line = `${new Date().toISOString()} ${gestureName} ${action} (${position[0]}, ${position[1]}) "${title}"\n`;
  fs.mkdirSync(path.dirname(path.resolve(currentPath)), { recursive: true });
  rotateIfNeeded();
  fs.appendFileSync(currentPath, line, "utf-8");
}
