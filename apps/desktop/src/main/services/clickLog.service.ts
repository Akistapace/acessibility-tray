import fs from "node:fs";
import path from "node:path";
import { foregroundWindowTitle } from "./win32.service";

// Desktop, not the install/cwd directory -- the whole point of this log is
// that a non-technical user can find it themselves without being told a
// path, the same way they'd find any other file they know to look for.
export function defaultLogPath(): string {
  return path.join(process.env.USERPROFILE ?? ".", "Desktop", "clicks.log");
}

let enabled = false;
let currentPath = defaultLogPath();
let maxBytesLimit = 1_000_000;
let backupCountLimit = 3;

export function enable(logPath: string = defaultLogPath(), maxBytes = 1_000_000, backupCount = 3): void {
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

export function record(
  gestureName: string,
  action: string,
  position: [number, number],
  windowTitleFn: () => string = foregroundWindowTitle
): void {
  if (!enabled) return;
  const title = windowTitleFn() || "?";
  const line = `${new Date().toISOString()} ${gestureName} ${action} (${position[0]}, ${position[1]}) "${title}"\n`;
  fs.mkdirSync(path.dirname(path.resolve(currentPath)), { recursive: true });
  rotateIfNeeded();
  fs.appendFileSync(currentPath, line, "utf-8");
}
