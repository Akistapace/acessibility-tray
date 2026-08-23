# Custom On-Screen Keyboard (Electron) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unreliable Windows-touch-keyboard toggle with a custom on-screen keyboard, built into the app, that types into any focused field via synthetic keystrokes.

**Architecture:** A new always-on-top, non-focusable `BrowserWindow` (`keyboardWindow.ts`), sibling to the existing `buttonsWindow.ts`/`overlayWindow.ts`, hosts an HTML/CSS/TS renderer that renders a QWERTY-based layout (plus a Portuguese accent row) and sends `keyboard:*` commands over the existing `mainRelay` IPC channel. Each key press resolves to a synthetic keystroke sent via nut-js (`keyboard.service.ts`), the same mechanism already used for the voice-typing Win+H shortcut. The old `ITipInvocation`/COM touch-keyboard code in `win32.service.ts` is deleted.

**Tech Stack:** Electron (BrowserWindow/IPC), TypeScript, `@nut-tree-fork/nut-js` (already a dependency), Vitest.

**Spec:** `docs/superpowers/specs/2026-08-23-custom-onscreen-keyboard-electron-design.md`

## Global Constraints

- The custom keyboard fully replaces the Windows touch keyboard — no toggle or fallback to the OS one.
- A Portuguese accent row (`Á Ã Â À É Ê Í Ó Ô Õ Ú Ç`) is always visible, in both compact and full mode.
- No Tab/arrow/Esc/Ctrl/Alt/Win/function keys — text entry only.
- No resize on compact/full toggle — the window is sized once for the "full" layout; toggling compact just hides rows, leaving transparent space.
- Keys are ~44px square — large targets for a head-tracked, non-pixel-precise cursor.
- The keyboard window uses `focusable:false` so a key click never steals focus from the real text field being typed into.
- Shift is a toggle (not a hold) and does not auto-release after one letter.
- `keyboard.type()` (nut-js) is called with plain unicode strings — no manual Shift-key sequencing, no dead-key composition.

---

### Task 1: `custom_keyboard` config field

**Files:**
- Modify: `apps/desktop/src/main/services/config.service.ts`
- Test: `apps/desktop/tests/config.test.ts`

**Interfaces:**
- Produces: `CustomKeyboardConfig { x: number | null; y: number | null; compact: boolean }`, `AppConfig.custom_keyboard: CustomKeyboardConfig`.

- [ ] **Step 1: Write the failing tests**

Add to `apps/desktop/tests/config.test.ts` (anywhere alongside the existing `action_buttons` tests):

```ts
describe("custom_keyboard", () => {
  it("defaults to centered/unset position and compact mode", () => {
    const cfg = configMod.defaultConfig();
    expect(cfg.custom_keyboard).toEqual({ x: null, y: null, compact: true });
  });

  it("drops unrecognized custom_keyboard position values to null", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(file, JSON.stringify({ custom_keyboard: { x: "nope", y: null, compact: true } }));
    const loaded = configMod.loadConfig(file);
    expect(loaded.custom_keyboard.x).toBeNull();
    expect(loaded.custom_keyboard.y).toBeNull();
  });

  it("falls back to compact=true for a non-boolean compact value", () => {
    const file = path.join(tmpDir, "config.json");
    fs.writeFileSync(file, JSON.stringify({ custom_keyboard: { compact: "nope" } }));
    expect(configMod.loadConfig(file).custom_keyboard.compact).toBe(true);
  });

  it("round-trips through configToDict/configFromDict", () => {
    const original = configMod.defaultConfig();
    original.custom_keyboard = { x: 40, y: 500, compact: false };

    const restored = configMod.configFromDict(configMod.configToDict(original));

    expect(restored.custom_keyboard).toEqual({ x: 40, y: 500, compact: false });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm --filter @facemesh-mouse/desktop test -- config.test.ts`
Expected: FAIL — `cfg.custom_keyboard` is `undefined`.

- [ ] **Step 3: Add `CustomKeyboardConfig` and wire it in**

In `apps/desktop/src/main/services/config.service.ts`, add the interface next to `ActionButtonsConfig` (around line 103-112):

```ts
export interface CustomKeyboardConfig {
  x: number | null;
  y: number | null;
  compact: boolean;
}
```

Add `custom_keyboard: CustomKeyboardConfig;` to the `AppConfig` interface (around line 152-157), next to `action_buttons`.

In `defaultConfig()` (around line 159-170), add `custom_keyboard: { x: null, y: null, compact: true }` to the returned object.

In `configFromDict()` (around line 192-244), after the existing `action_buttons` block, add:

```ts
const rawKeyboard = (raw.custom_keyboard as Record<string, unknown>) ?? {};
const compactRaw = rawKeyboard.compact;
const custom_keyboard: CustomKeyboardConfig = {
  x: optionalFloat(rawKeyboard.x),
  y: optionalFloat(rawKeyboard.y),
  compact: typeof compactRaw === "boolean" ? compactRaw : fallback.custom_keyboard.compact,
};
```

and add `custom_keyboard` to the object returned at the end of `configFromDict` (next to `action_buttons`, `cursor`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm --filter @facemesh-mouse/desktop test -- config.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/main/services/config.service.ts apps/desktop/tests/config.test.ts
git commit -m "feat(config): add custom_keyboard position/mode field"
```

---

### Task 2: Synthetic-typing helpers in `keyboard.service.ts`

**Files:**
- Modify: `apps/desktop/src/main/services/keyboard.service.ts`
- Test: `apps/desktop/tests/keyboard.service.test.ts` (new)

**Interfaces:**
- Produces: `typeText(text: string): Promise<void>`, `pressBackspace(): Promise<void>`, `pressEnter(): Promise<void>`.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/tests/keyboard.service.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach } from "vitest";

const typeMock = vi.fn();
const pressKeyMock = vi.fn();
const releaseKeyMock = vi.fn();

vi.mock("@nut-tree-fork/nut-js", () => ({
  keyboard: { type: typeMock, pressKey: pressKeyMock, releaseKey: releaseKeyMock },
  Key: { Backspace: "Backspace", Return: "Return" },
}));

import { typeText, pressBackspace, pressEnter } from "../src/main/services/keyboard.service";

describe("keyboard.service custom-keyboard helpers", () => {
  beforeEach(() => {
    typeMock.mockClear();
    pressKeyMock.mockClear();
    releaseKeyMock.mockClear();
  });

  it("typeText types the given text through nut-js", async () => {
    await typeText("á");
    expect(typeMock).toHaveBeenCalledWith("á");
  });

  it("pressBackspace presses and releases Backspace", async () => {
    await pressBackspace();
    expect(pressKeyMock).toHaveBeenCalledWith("Backspace");
    expect(releaseKeyMock).toHaveBeenCalledWith("Backspace");
  });

  it("pressEnter presses and releases Return (the main Enter key, not numpad Enter)", async () => {
    await pressEnter();
    expect(pressKeyMock).toHaveBeenCalledWith("Return");
    expect(releaseKeyMock).toHaveBeenCalledWith("Return");
  });

  it("typeText swallows a nut-js failure instead of throwing", async () => {
    typeMock.mockRejectedValueOnce(new Error("boom"));
    await expect(typeText("x")).resolves.toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @facemesh-mouse/desktop test -- keyboard.service.test.ts`
Expected: FAIL — `typeText`/`pressBackspace`/`pressEnter` are not exported.

- [ ] **Step 3: Implement the helpers**

In `apps/desktop/src/main/services/keyboard.service.ts`, add below the existing `toggleVoiceTyping`:

```ts
export async function typeText(text: string): Promise<void> {
  try {
    const { keyboard } = await import("@nut-tree-fork/nut-js");
    await keyboard.type(text);
  } catch (exc) {
    console.error(`facemesh-mouse: could not type text (${exc})`);
  }
}

export async function pressBackspace(): Promise<void> {
  try {
    const { keyboard, Key } = await import("@nut-tree-fork/nut-js");
    await keyboard.pressKey(Key.Backspace);
    await keyboard.releaseKey(Key.Backspace);
  } catch (exc) {
    console.error(`facemesh-mouse: could not press backspace (${exc})`);
  }
}

export async function pressEnter(): Promise<void> {
  try {
    const { keyboard, Key } = await import("@nut-tree-fork/nut-js");
    // Key.Return is the main keyboard's Enter key; Key.Enter is numpad Enter.
    await keyboard.pressKey(Key.Return);
    await keyboard.releaseKey(Key.Return);
  } catch (exc) {
    console.error(`facemesh-mouse: could not press enter (${exc})`);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @facemesh-mouse/desktop test -- keyboard.service.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/main/services/keyboard.service.ts apps/desktop/tests/keyboard.service.test.ts
git commit -m "feat(keyboard): add nut-js typeText/pressBackspace/pressEnter helpers"
```

---

### Task 3: `keyboardPosition.ts` — window sizing and placement

**Files:**
- Create: `apps/desktop/src/main/windows/keyboardPosition.ts`
- Test: `apps/desktop/tests/keyboardPosition.test.ts`

**Interfaces:**
- Produces: `KEY_SIZE`, `KEY_GAP`, `PADDING`, `HANDLE_HEIGHT`, `WIDTH`, `WINDOW_HEIGHT`, `MARGIN` (numbers); `Point { x: number; y: number }`; `defaultPosition(screenW, screenH, taskbarReservedPx?): Point`; `resolvePosition(savedX, savedY, screenW, screenH, taskbarReservedPx?): Point`.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/tests/keyboardPosition.test.ts` (mirrors `tests/position.test.ts`):

```ts
import { describe, expect, it } from "vitest";
import { WIDTH, WINDOW_HEIGHT, MARGIN, defaultPosition, resolvePosition } from "../src/main/windows/keyboardPosition";

describe("defaultPosition", () => {
  it("centers horizontally, insets from the bottom", () => {
    expect(defaultPosition(1000, 800)).toEqual({
      x: (1000 - WIDTH) / 2,
      y: 800 - WINDOW_HEIGHT - MARGIN,
    });
  });

  it("sits above a reserved taskbar", () => {
    expect(defaultPosition(1000, 800, 48)).toEqual({
      x: (1000 - WIDTH) / 2,
      y: 800 - WINDOW_HEIGHT - MARGIN - 48,
    });
  });
});

describe("resolvePosition", () => {
  it("uses the saved spot when it still fits", () => {
    expect(resolvePosition(50, 60, 1000, 800)).toEqual({ x: 50, y: 60 });
  });

  it("falls back to default without a saved spot", () => {
    expect(resolvePosition(null, null, 1000, 800)).toEqual(defaultPosition(1000, 800));
  });

  it("falls back when the saved spot is off a smaller screen", () => {
    expect(resolvePosition(1900, 1000, 1000, 800)).toEqual(defaultPosition(1000, 800));
  });

  it("accepts the saved spot exactly at the far edge", () => {
    const edgeX = 1000 - WIDTH;
    const edgeY = 800 - WINDOW_HEIGHT;
    expect(resolvePosition(edgeX, edgeY, 1000, 800)).toEqual({ x: edgeX, y: edgeY });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @facemesh-mouse/desktop test -- keyboardPosition.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `keyboardPosition.ts`**

Create `apps/desktop/src/main/windows/keyboardPosition.ts`:

```ts
// Key size/gap here must match renderer/keyboard/style.css's .key width and
// #keys gap -- there's no shared build-time constant between main and
// renderer CSS, so keep these two in sync by hand.
export const KEY_SIZE = 44;
export const KEY_GAP = 6;
export const PADDING = 12;
export const HANDLE_HEIGHT = 26;
export const MARGIN = 24;

// Widest row is the 12-key accent row (Á Ã Â À É Ê Í Ó Ô Õ Ú Ç), wider than
// either the 10-key letter/number rows -- that sets the window width.
const WIDEST_ROW_KEYS = 12;
export const WIDTH = KEY_SIZE * WIDEST_ROW_KEYS + KEY_GAP * (WIDEST_ROW_KEYS - 1) + PADDING * 2;

// "Full" mode is the tallest case: numbers row + punctuation row + 3 letter
// rows + accent row + bottom row = 7 rows. The window is sized for this
// once and never resized when toggling to compact (see design spec).
const FULL_MODE_ROW_COUNT = 7;
export const WINDOW_HEIGHT =
  HANDLE_HEIGHT + FULL_MODE_ROW_COUNT * KEY_SIZE + (FULL_MODE_ROW_COUNT - 1) * KEY_GAP + PADDING;

export interface Point {
  x: number;
  y: number;
}

export function defaultPosition(screenW: number, screenH: number, taskbarReservedPx = 0): Point {
  return { x: (screenW - WIDTH) / 2, y: screenH - WINDOW_HEIGHT - MARGIN - taskbarReservedPx };
}

export function resolvePosition(
  savedX: number | null,
  savedY: number | null,
  screenW: number,
  screenH: number,
  taskbarReservedPx = 0
): Point {
  if (savedX === null || savedY === null) {
    return defaultPosition(screenW, screenH, taskbarReservedPx);
  }
  if (
    !(savedX >= 0 && savedX <= screenW - WIDTH) ||
    !(savedY >= 0 && savedY <= screenH - WINDOW_HEIGHT)
  ) {
    return defaultPosition(screenW, screenH, taskbarReservedPx);
  }
  return { x: savedX, y: savedY };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @facemesh-mouse/desktop test -- keyboardPosition.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/main/windows/keyboardPosition.ts apps/desktop/tests/keyboardPosition.test.ts
git commit -m "feat(keyboard): add keyboard window sizing/placement helpers"
```

---

### Task 4: `renderer/keyboard/layout.ts` — pure layout data

**Files:**
- Create: `apps/desktop/src/renderer/keyboard/layout.ts`
- Test: `apps/desktop/tests/keyboardLayout.test.ts`

**Interfaces:**
- Produces: `LETTER_ROWS: readonly string[][]`, `ACCENT_ROW: readonly string[]`, `FULL_EXTRA_ROWS: readonly string[][]`, `keyOutput(char: string, shiftActive: boolean): string`.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/tests/keyboardLayout.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { LETTER_ROWS, ACCENT_ROW, FULL_EXTRA_ROWS, keyOutput } from "../src/renderer/keyboard/layout";

describe("keyboard layout data", () => {
  it("has three QWERTY letter rows", () => {
    expect(LETTER_ROWS).toEqual([
      [..."QWERTYUIOP"],
      [..."ASDFGHJKL"],
      [..."ZXCVBNM"],
    ]);
  });

  it("accent row has the Portuguese accented characters", () => {
    expect(ACCENT_ROW).toEqual([..."ÁÃÂÀÉÊÍÓÔÕÚ", "Ç"]);
  });

  it("full-mode extra rows are numbers then punctuation", () => {
    expect(FULL_EXTRA_ROWS).toEqual([[..."1234567890"], [",", ".", "-", "?"]]);
  });
});

describe("keyOutput", () => {
  it("lowercases when shift is not active", () => {
    expect(keyOutput("Q", false)).toBe("q");
  });

  it("uppercases when shift is active", () => {
    expect(keyOutput("q", true)).toBe("Q");
  });

  it("uppercases an accented character when shift is active", () => {
    expect(keyOutput("á", true)).toBe("Á");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @facemesh-mouse/desktop test -- keyboardLayout.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `layout.ts`**

Create `apps/desktop/src/renderer/keyboard/layout.ts`:

```ts
export const LETTER_ROWS: readonly string[][] = [
  [..."QWERTYUIOP"],
  [..."ASDFGHJKL"],
  [..."ZXCVBNM"],
];

// Always visible in both compact and full mode -- Portuguese text needs
// these too often to gate behind the "full" toggle.
export const ACCENT_ROW: readonly string[] = [..."ÁÃÂÀÉÊÍÓÔÕÚ", "Ç"];

// Full mode only, rendered above the letter grid.
export const FULL_EXTRA_ROWS: readonly string[][] = [
  [..."1234567890"],
  [",", ".", "-", "?"],
];

export function keyOutput(char: string, shiftActive: boolean): string {
  return shiftActive ? char.toUpperCase() : char.toLowerCase();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @facemesh-mouse/desktop test -- keyboardLayout.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/keyboard/layout.ts apps/desktop/tests/keyboardLayout.test.ts
git commit -m "feat(keyboard): add on-screen keyboard layout data"
```

---

### Task 5: `keyboardWindow.ts` — the BrowserWindow

**Files:**
- Create: `apps/desktop/src/main/windows/keyboardWindow.ts`
- Test: `apps/desktop/tests/keyboardWindow.test.ts`

**Interfaces:**
- Consumes: `defaultPosition`, `resolvePosition`, `WIDTH`, `WINDOW_HEIGHT` from `./keyboardPosition` (Task 3); `BackendServer` type (structural — only `.send(command)` is used, same as `buttonsWindow.ts`).
- Produces: `createKeyboardWindow(backend, savedX: number | null, savedY: number | null): BrowserWindow`, `showKeyboardWindow(): void`, `hideKeyboardWindow(): void`, `moveKeyboardWindow(dx: number, dy: number): void`, `endKeyboardDrag(): void`, `resetKeyboardPosition(): void`.

- [ ] **Step 1: Write the failing tests**

Create `apps/desktop/tests/keyboardWindow.test.ts` (mirrors `tests/buttonsWindow.test.ts`):

```ts
import { describe, expect, it, vi, beforeEach } from "vitest";

class FakeBrowserWindow {
  static instances: FakeBrowserWindow[] = [];
  on = vi.fn();
  loadFile = vi.fn();
  showInactive = vi.fn();
  hide = vi.fn();
  getPosition = vi.fn(() => [100, 200]);
  setPosition = vi.fn((x: number, y: number) => {
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      throw new TypeError("Error processing argument at index 0, conversion failure from");
    }
  });

  constructor() {
    FakeBrowserWindow.instances.push(this);
  }
}

vi.mock("electron", () => ({
  BrowserWindow: FakeBrowserWindow,
  screen: {
    getPrimaryDisplay: () => ({
      bounds: { width: 1920, height: 1080 },
      workArea: { height: 1040 },
    }),
  },
}));

describe("keyboardWindow", () => {
  beforeEach(() => {
    vi.resetModules();
    FakeBrowserWindow.instances = [];
  });

  it("moveKeyboardWindow adds the delta to the current position", async () => {
    const { createKeyboardWindow, moveKeyboardWindow } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send: vi.fn() } as never, null, null);

    moveKeyboardWindow(5, -3);

    expect(FakeBrowserWindow.instances[0].setPosition).toHaveBeenCalledWith(105, 197);
  });

  it("ignores a malformed delta instead of crashing the main process", async () => {
    const { createKeyboardWindow, moveKeyboardWindow } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send: vi.fn() } as never, null, null);

    expect(() => moveKeyboardWindow(undefined as unknown as number, 5)).not.toThrow();

    expect(FakeBrowserWindow.instances[0].setPosition).not.toHaveBeenCalled();
  });

  it("endKeyboardDrag saves the current position through the backend", async () => {
    const send = vi.fn();
    const { createKeyboardWindow, endKeyboardDrag } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send } as never, null, null);

    endKeyboardDrag();

    expect(send).toHaveBeenCalledWith({
      type: "save_config",
      config: { custom_keyboard: { x: 100, y: 200 } },
    });
  });

  it("showKeyboardWindow shows the window without activating it", async () => {
    const { createKeyboardWindow, showKeyboardWindow } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send: vi.fn() } as never, null, null);

    showKeyboardWindow();

    expect(FakeBrowserWindow.instances[0].showInactive).toHaveBeenCalled();
  });

  it("hideKeyboardWindow hides the window", async () => {
    const { createKeyboardWindow, hideKeyboardWindow } = await import("../src/main/windows/keyboardWindow");
    createKeyboardWindow({ send: vi.fn() } as never, null, null);

    hideKeyboardWindow();

    expect(FakeBrowserWindow.instances[0].hide).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm --filter @facemesh-mouse/desktop test -- keyboardWindow.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `keyboardWindow.ts`**

Create `apps/desktop/src/main/windows/keyboardWindow.ts`:

```ts
import { BrowserWindow, screen } from "electron";
import path from "node:path";
import type { BackendServer } from "../services/backendServer";
import { defaultPosition, resolvePosition, WIDTH, WINDOW_HEIGHT } from "./keyboardPosition";

let win: BrowserWindow | null = null;
let backendRef: BackendServer | null = null;

export function createKeyboardWindow(
  backend: BackendServer,
  savedX: number | null,
  savedY: number | null
): BrowserWindow {
  backendRef = backend;
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().bounds;
  const taskbarReservedPx = screenH - screen.getPrimaryDisplay().workArea.height;
  const { x, y } = resolvePosition(savedX, savedY, screenW, screenH, taskbarReservedPx);

  win = new BrowserWindow({
    x: Math.round(x),
    y: Math.round(y),
    width: WIDTH,
    height: WINDOW_HEIGHT,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    // Starts hidden -- shown only when the ⌨ button sends open_keyboard.
    // Never destroyed, so shift state / compact-vs-full mode in the
    // renderer's JS survives across opens for the rest of the process's life.
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "keyboard", "index.html"));

  return win;
}

export function showKeyboardWindow(): void {
  win?.showInactive();
}

export function hideKeyboardWindow(): void {
  win?.hide();
}

export function moveKeyboardWindow(dx: number, dy: number): void {
  if (!win) return;
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return;
  const [curX, curY] = win.getPosition();
  win.setPosition(curX + dx, curY + dy);
}

export function endKeyboardDrag(): void {
  if (!win || !backendRef) return;
  const [curX, curY] = win.getPosition();
  backendRef.send({
    type: "save_config",
    config: { custom_keyboard: { x: curX, y: curY } },
  });
}

export function resetKeyboardPosition(): void {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().bounds;
  const taskbarReservedPx = screenH - screen.getPrimaryDisplay().workArea.height;
  const { x, y } = defaultPosition(screenW, screenH, taskbarReservedPx);
  win?.setPosition(Math.round(x), Math.round(y));
}
```

Note: the window is created without `.showInactive()`/`.show()` at the end of
`createKeyboardWindow` (unlike `buttonsWindow.ts`, which is always visible) —
it stays hidden until `showKeyboardWindow()` is called. `BrowserWindow`
defaults to `show: true` on construction, so this relies on nothing calling
`.show()`; Electron's real `BrowserWindow` actually shows itself once ready
unless `show: false` is passed. Pass `show: false` explicitly in the options
object above (add `show: false,` next to `resizable: false,`) so it truly
starts hidden.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm --filter @facemesh-mouse/desktop test -- keyboardWindow.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/main/windows/keyboardWindow.ts apps/desktop/tests/keyboardWindow.test.ts
git commit -m "feat(keyboard): add the keyboard overlay BrowserWindow"
```

---

### Task 6: `keyboard.ipc.ts` — wire the renderer's commands

**Files:**
- Create: `apps/desktop/src/main/ipc/keyboard.ipc.ts`
- Modify: `apps/desktop/src/main/ipc/index.ts`
- Modify: `apps/desktop/src/main/ipc/config.ipc.ts`

**Interfaces:**
- Consumes: `mainRelay` from `./relay`; `moveKeyboardWindow`, `endKeyboardDrag`, `hideKeyboardWindow`, `resetKeyboardPosition` from `../windows/keyboardWindow` (Task 5); `typeText`, `pressBackspace`, `pressEnter` from `../services/keyboard.service` (Task 2).
- Produces: `registerKeyboardIpc(): void`.

This task has no dedicated test file — same as `buttons.ipc.ts`, which has
none today. It's thin wiring over already-tested pieces (`keyboardWindow.ts`,
`keyboard.service.ts`); its own correctness is exercised by the manual smoke
test in Task 10.

- [ ] **Step 1: Create `keyboard.ipc.ts`**

Create `apps/desktop/src/main/ipc/keyboard.ipc.ts`:

```ts
import { mainRelay } from "./relay";
import { moveKeyboardWindow, endKeyboardDrag, hideKeyboardWindow } from "../windows/keyboardWindow";
import { typeText, pressBackspace, pressEnter } from "../services/keyboard.service";

export function registerKeyboardIpc(): void {
  mainRelay.on("keyboard:type", (message: { text: string }) => {
    void typeText(message.text);
  });
  mainRelay.on("keyboard:backspace", () => {
    void pressBackspace();
  });
  mainRelay.on("keyboard:enter", () => {
    void pressEnter();
  });
  mainRelay.on("keyboard:drag-move", (message: { dx: number; dy: number }) => {
    moveKeyboardWindow(message.dx, message.dy);
  });
  mainRelay.on("keyboard:drag-end", () => {
    endKeyboardDrag();
  });
  mainRelay.on("keyboard:close", () => {
    hideKeyboardWindow();
  });
}
```

- [ ] **Step 2: Register it in `ipc/index.ts`**

In `apps/desktop/src/main/ipc/index.ts`, add the import and call:

```ts
import type { BackendServer } from "../services/backendServer";
import { wireBackendRelay } from "./relay";
import { registerConfigIpc } from "./config.ipc";
import { registerButtonsIpc } from "./buttons.ipc";
import { registerKeyboardIpc } from "./keyboard.ipc";
import { registerTrackingIpc } from "./tracking.ipc";

export function wireIpc(backend: BackendServer): void {
  wireBackendRelay(backend);
  registerConfigIpc();
  registerButtonsIpc();
  registerKeyboardIpc();
  registerTrackingIpc(backend);
}
```

- [ ] **Step 3: Also reset the keyboard panel's position from the Extras "reset position" button**

The config window's "Redefinir posição do teclado/microfone" button already
resets the ⌨/🎤 circle-buttons window via `config:reset-position`. Since the
keyboard panel is now a separate draggable window, it should reset too. In
`apps/desktop/src/main/ipc/config.ipc.ts`:

```ts
import { mainRelay } from "./relay";
import { resetButtonsPosition } from "../windows/buttonsWindow";
import { resetKeyboardPosition } from "../windows/keyboardWindow";

export function registerConfigIpc(): void {
  mainRelay.on("config:reset-position", () => {
    resetButtonsPosition();
    resetKeyboardPosition();
  });
}
```

- [ ] **Step 4: Typecheck**

Run: `pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.json`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/main/ipc/keyboard.ipc.ts apps/desktop/src/main/ipc/index.ts apps/desktop/src/main/ipc/config.ipc.ts
git commit -m "feat(keyboard): wire keyboard:* IPC commands to the window and typing helpers"
```

---

### Task 7: Keyboard renderer UI (HTML/CSS/TS) + build registration

**Files:**
- Create: `apps/desktop/src/renderer/keyboard/index.html`
- Create: `apps/desktop/src/renderer/keyboard/style.css`
- Create: `apps/desktop/src/renderer/keyboard/index.ts`
- Modify: `apps/desktop/scripts/buildRenderer.mjs`
- Modify: `apps/desktop/tsconfig.renderer.json`

**Interfaces:**
- Consumes: `LETTER_ROWS`, `ACCENT_ROW`, `FULL_EXTRA_ROWS`, `keyOutput` from `./layout` (Task 4); `window.backend.send`/`window.backend.on` from `window.d.ts` (unchanged); IPC channel names from Task 6 (`keyboard:type`, `keyboard:backspace`, `keyboard:enter`, `keyboard:drag-move`, `keyboard:drag-end`, `keyboard:close`) and the existing `get_config`/`config`/`save_config` channels.

This is DOM-event-wiring code, like `renderer/buttons/index.ts` — the
codebase has no automated test for that file either (its logic lives in the
already-tested `layout.ts` and `keyboardWindow.ts`/`keyboard.service.ts`).
Verified by the build step below and the manual smoke test in Task 10.

- [ ] **Step 1: `index.html`**

Create `apps/desktop/src/renderer/keyboard/index.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>keyboard</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="title-strip">
    <div id="drag-handle" title="Arrastar"></div>
    <button id="mode-toggle" title="Alternar layout completo/compacto">123</button>
    <button id="close-button" title="Fechar">✕</button>
  </div>
  <div id="keys"></div>
  <script type="module" src="index.js"></script>
</body>
</html>
```

- [ ] **Step 2: `style.css`**

Create `apps/desktop/src/renderer/keyboard/style.css`:

```css
html, body {
  margin: 0;
  width: 100vw;
  height: 100vh;
  background: transparent;
  overflow: hidden;
  user-select: none;
  font-family: "Segoe UI", sans-serif;
}

#title-strip {
  display: flex;
  align-items: center;
  height: 26px;
  padding: 0 6px;
  gap: 6px;
  box-sizing: border-box;
}

#drag-handle {
  flex: 1;
  height: 16px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.16);
  cursor: grab;
}
#drag-handle:active { cursor: grabbing; }

#mode-toggle, #close-button {
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  cursor: pointer;
  font-size: 11px;
  line-height: 22px;
  padding: 0;
}
#close-button { background: rgba(255, 80, 80, 0.35); }

/* .key width + #keys gap must match keyboardPosition.ts's KEY_SIZE/KEY_GAP
   -- there's no shared constant between main and renderer CSS here. */
#keys {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 12px 12px;
  box-sizing: border-box;
}

.row {
  display: flex;
  gap: 6px;
  justify-content: center;
}

.key {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 6px;
  background: #2d2d2d;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  padding: 0;
}
.key:active { background: #4da3ff; }

.shift-key.active { background: #4da3ff; }
.space-key { flex: 1; }
```

- [ ] **Step 3: `index.ts`**

Create `apps/desktop/src/renderer/keyboard/index.ts`:

```ts
import { LETTER_ROWS, ACCENT_ROW, FULL_EXTRA_ROWS, keyOutput } from "./layout.js";

let shiftActive = false;
let compact = true;

const keysContainer = document.getElementById("keys") as HTMLDivElement;
const modeToggle = document.getElementById("mode-toggle") as HTMLButtonElement;
const closeButton = document.getElementById("close-button") as HTMLButtonElement;
const dragHandle = document.getElementById("drag-handle") as HTMLDivElement;

function makeKey(label: string, onClick: () => void, extraClass?: string): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.className = extraClass ? `key ${extraClass}` : "key";
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function makeRow(chars: readonly string[]): HTMLDivElement {
  const row = document.createElement("div");
  row.className = "row";
  for (const char of chars) {
    row.appendChild(
      makeKey(char, () => {
        window.backend.send({ type: "keyboard:type", text: keyOutput(char, shiftActive) });
      })
    );
  }
  return row;
}

function render(): void {
  keysContainer.innerHTML = "";
  if (!compact) {
    for (const row of FULL_EXTRA_ROWS) keysContainer.appendChild(makeRow(row));
  }
  for (const row of LETTER_ROWS) keysContainer.appendChild(makeRow(row));
  keysContainer.appendChild(makeRow(ACCENT_ROW));

  const bottomRow = document.createElement("div");
  bottomRow.className = "row";
  const shiftKey = makeKey(
    "⇧",
    () => {
      shiftActive = !shiftActive;
      shiftKey.classList.toggle("active", shiftActive);
    },
    "shift-key"
  );
  const spaceKey = makeKey(
    " ",
    () => window.backend.send({ type: "keyboard:type", text: " " }),
    "space-key"
  );
  const backspaceKey = makeKey("⌫", () => window.backend.send({ type: "keyboard:backspace" }));
  const enterKey = makeKey("⏎", () => window.backend.send({ type: "keyboard:enter" }));
  bottomRow.append(shiftKey, spaceKey, backspaceKey, enterKey);
  keysContainer.appendChild(bottomRow);
}

modeToggle.addEventListener("click", () => {
  compact = !compact;
  render();
  window.backend.send({ type: "save_config", config: { custom_keyboard: { compact } } });
});

closeButton.addEventListener("click", () => {
  window.backend.send({ type: "keyboard:close" });
});

// Same press/move/threshold-free drag pattern as buttons/index.ts's
// drag-handle -- the whole strip is the drag target, individual keys never
// double as one.
let lastMovePos: { x: number; y: number } | null = null;

dragHandle.addEventListener("pointerdown", (event) => {
  lastMovePos = { x: event.screenX, y: event.screenY };
  (event.target as HTMLElement).setPointerCapture(event.pointerId);
});

dragHandle.addEventListener("pointermove", (event) => {
  if (!lastMovePos || event.buttons !== 1) return;
  const dx = event.screenX - lastMovePos.x;
  const dy = event.screenY - lastMovePos.y;
  if (dx !== 0 || dy !== 0) {
    window.backend.send({ type: "keyboard:drag-move", dx, dy });
    lastMovePos = { x: event.screenX, y: event.screenY };
  }
});

dragHandle.addEventListener("pointerup", () => {
  if (!lastMovePos) return;
  lastMovePos = null;
  window.backend.send({ type: "keyboard:drag-end" });
});

window.backend.on("config", (message) => {
  const { config } = message as { config?: { custom_keyboard?: { compact?: boolean } } };
  compact = config?.custom_keyboard?.compact !== false;
  render();
});

window.backend.send({ type: "get_config" });
render();
```

- [ ] **Step 4: Register the new renderer entry point in the build**

In `apps/desktop/scripts/buildRenderer.mjs`, add `"keyboard"` to
`RENDERER_ENTRIES` (line 12):

```js
const RENDERER_ENTRIES = ["buttons", "config", "keyboard", "overlay", "tracking"];
```

- [ ] **Step 5: Include the new renderer directory in the renderer typecheck**

In `apps/desktop/tsconfig.renderer.json`, add `"src/renderer/keyboard"` to
`include`:

```json
"include": ["src/renderer/window.d.ts", "src/renderer/buttons", "src/renderer/config", "src/renderer/keyboard", "src/renderer/overlay", "src/renderer/tracking"]
```

- [ ] **Step 6: Build and verify the new bundle is produced**

Run: `pnpm --filter @facemesh-mouse/desktop run build`
Expected: succeeds; `apps/desktop/dist/renderer/keyboard/index.js`,
`index.html`, and `style.css` exist.

- [ ] **Step 7: Commit**

```bash
git add apps/desktop/src/renderer/keyboard apps/desktop/scripts/buildRenderer.mjs apps/desktop/tsconfig.renderer.json
git commit -m "feat(keyboard): add the on-screen keyboard renderer UI"
```

---

### Task 8: `backendServer.ts` — swap the touch-keyboard dep for `openKeyboard`

**Files:**
- Modify: `apps/desktop/src/main/services/backendServer.ts`
- Test: `apps/desktop/tests/backendServer.test.ts`

**Interfaces:**
- Produces: `BackendServerDeps.openKeyboard?: () => void` (replaces `toggleTouchKeyboard?: () => Promise<boolean>`).

- [ ] **Step 1: Update the failing/changing test**

In `apps/desktop/tests/backendServer.test.ts`, replace the existing
"open_keyboard reports keyboard_result using the injected toggle" test
(around line 210-221) with:

```ts
  it("open_keyboard calls the injected openKeyboard and always reports opened:true", async () => {
    let called = false;
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({
      engine, config: configMod.defaultConfig(),
      openKeyboard: () => { called = true; },
    });
    const messagePromise = waitForMessage(server, "keyboard_result");

    await server.send({ type: "open_keyboard", x: 100, y: 200 });

    expect(await messagePromise).toEqual({ type: "keyboard_result", opened: true, x: 100, y: 200 });
    expect(called).toBe(true);
  });

  it("open_keyboard still reports opened:true with no openKeyboard dep injected", async () => {
    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig() });
    const messagePromise = waitForMessage(server, "keyboard_result");

    await server.send({ type: "open_keyboard", x: 1, y: 2 });

    expect(await messagePromise).toEqual({ type: "keyboard_result", opened: true, x: 1, y: 2 });
  });
```

Also add a `save_config` merge test for `custom_keyboard`, next to the
existing `action_buttons`/`cursor` merge tests (around line 138-153):

```ts
  it("save_config merges a partial custom_keyboard payload onto the existing file", async () => {
    const file = path.join(tmpDir, "config.json");
    const seed = configMod.defaultConfig();
    seed.custom_keyboard = { x: 10, y: 20, compact: false };
    configMod.saveConfig(file, seed);

    const engine = new TrackingEngine(configMod.defaultConfig(), new FakeMouseDriver(), [1000, 1000]);
    const server = new BackendServer({ engine, config: configMod.defaultConfig(), configPath: file });

    await server.send({ type: "save_config", config: { custom_keyboard: { compact: true } } });

    const reloaded = configMod.loadConfig(file);
    expect(reloaded.custom_keyboard).toEqual({ x: 10, y: 20, compact: true });
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm --filter @facemesh-mouse/desktop test -- backendServer.test.ts`
Expected: FAIL — `openKeyboard` isn't a recognized dep; `custom_keyboard` merge doesn't happen.

- [ ] **Step 3: Update `backendServer.ts`**

In `apps/desktop/src/main/services/backendServer.ts`:

Replace the `toggleTouchKeyboard` field in `BackendServerDeps` (line 25) with:

```ts
  openKeyboard?: () => void;
```

Replace `toggleTouchKeyboardImpl` (line 36) with:

```ts
  private readonly openKeyboardImpl: () => void;
```

Replace its assignment in the constructor (line 50) with:

```ts
    this.openKeyboardImpl = deps.openKeyboard ?? (() => {});
```

Replace the `case "open_keyboard"` block (lines 188-194) with:

```ts
        case "open_keyboard": {
          const x = Number(command.x ?? 0);
          const y = Number(command.y ?? 0);
          this.openKeyboardImpl();
          this.emit("message", { type: "keyboard_result", opened: true, x, y });
          break;
        }
```

In `case "save_config"` (around line 161-187), add a `custom_keyboard` merge
branch alongside the existing `action_buttons`/`cursor` ones:

```ts
          if (payload.custom_keyboard) {
            merged.custom_keyboard = { ...(onDiskDict.custom_keyboard as object), ...(payload.custom_keyboard as object) };
          }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm --filter @facemesh-mouse/desktop test -- backendServer.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/main/services/backendServer.ts apps/desktop/tests/backendServer.test.ts
git commit -m "refactor(backend): open_keyboard calls a synchronous openKeyboard dep, always opens"
```

---

### Task 9: Overlay pulse cleanup — drop the OS-failure warning path

**Files:**
- Modify: `apps/desktop/src/renderer/overlay/index.ts`
- Modify: `apps/desktop/src/renderer/overlay/index.html`
- Modify: `apps/desktop/src/renderer/overlay/style.css`
- Modify: `apps/desktop/src/renderer/overlay/pulse.ts`

**Interfaces:**
- No change to `pulseRadius` (still covered by `tests/pulse.test.ts`, untouched).

Since Task 8 makes `keyboard_result.opened` always `true`, the red
warning-pulse + tooltip branch in the overlay (added to compensate for the
old OS toggle's silent failures) is now dead code. No test currently covers
it (`tests/pulse.test.ts` only tests `pulseRadius`), so this is a plain
removal with no test changes needed.

- [ ] **Step 1: Simplify the `keyboard_result` handler**

In `apps/desktop/src/renderer/overlay/index.ts`, remove the `tooltip` const,
the `showTooltip` function, and the `WARNING_COLOR` import, then replace the
`keyboard_result` handler (lines 52-61) with:

```ts
window.backend.on("keyboard_result", (message) => {
  const result = message as { x: number; y: number };
  const { x, y } = toLocal(result.x, result.y);
  drawPulse(x, y, RING_COLOR);
});
```

The import line (line 1) becomes:

```ts
import { pulseRadius, RING_COLOR, START_RADIUS, END_RADIUS, DURATION_MS } from "./pulse.js";
```

- [ ] **Step 2: Remove the now-unused tooltip element and style**

In `apps/desktop/src/renderer/overlay/index.html`, remove line 10:
`<div id="tooltip" class="tooltip"></div>`.

In `apps/desktop/src/renderer/overlay/style.css`, remove the `.tooltip { ... }`
rule (lines 4-13).

- [ ] **Step 3: Remove the now-unused `WARNING_COLOR` export**

In `apps/desktop/src/renderer/overlay/pulse.ts`, remove line 9:
`export const WARNING_COLOR = "#ff4d4d";`.

- [ ] **Step 4: Run the full test suite and typecheck**

Run: `pnpm --filter @facemesh-mouse/desktop test`
Expected: PASS (no test referenced the removed code).

Run: `pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.renderer.json`
Expected: no errors (confirms nothing else imports `WARNING_COLOR`).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/overlay
git commit -m "refactor(overlay): drop the open_keyboard failure warning pulse/tooltip"
```

---

### Task 10: Final wiring — `main/index.ts`, delete the old touch-keyboard code, Extras copy

**Files:**
- Modify: `apps/desktop/src/main/index.ts`
- Modify: `apps/desktop/src/main/services/win32.service.ts`
- Modify: `apps/desktop/src/renderer/config/index.html`

**Interfaces:**
- Consumes: `createKeyboardWindow`, `showKeyboardWindow` from `./windows/keyboardWindow` (Task 5); `config.custom_keyboard.x`/`.y` from `config.service.ts` (Task 1).

This is the integration point where the new keyboard window actually gets
created and wired into the running app, and where the old dead code is
removed — it's reviewed as one unit since the old and new paths can't
coexist (removing the `toggleTouchKeyboard` dep in Task 8 already made
`main/index.ts` reference something that no longer exists on
`BackendServerDeps`, so this task is also what makes the whole app compile
again end to end... note: Task 8 removed `toggleTouchKeyboard` from
`BackendServerDeps` but TypeScript's excess-property checks only apply to
object literals assigned directly, so `main/index.ts` passing a stray
`toggleTouchKeyboard` field would in fact still fail to typecheck since it's
an inline object literal — that's expected and is fixed by this task, not a
regression to worry about).

- [ ] **Step 1: Delete the touch-keyboard code from `win32.service.ts`**

In `apps/desktop/src/main/services/win32.service.ts`, delete:
- Functions: `toggleTouchKeyboard`, `preferFloatingLayout`, `touchKeyboardVisible`, `guidBuffer`, `sleep`.
- Constants: `CLSID_UI_HOST_NO_LAUNCH`, `IID_ITIP_INVOCATION`, `CLSCTX_ALL`, `COINIT_APARTMENTTHREADED`, `S_OK`, `S_FALSE`, `HKEY_CURRENT_USER`, `TABLET_TIP_KEY`, `EDGE_TARGET_DOCKED_STATE`, `REG_DWORD`, `DOCKED_STATE_FLOATING`, `TOUCH_KEYBOARD_WINDOW_CLASS`, `VISIBILITY_POLL_INTERVAL_MS`, `VISIBILITY_POLL_ATTEMPTS`.
- Bindings: the `ole32`/`advapi32` `koffi.load()` calls, and `CoInitializeEx`, `CoUninitialize`, `CLSIDFromString`, `CoCreateInstance`, `RegCreateKeyExW`, `RegSetValueExW`, `RegCloseKey`, `FindWindowW`, `IsWindowVisible`.

What remains in the file after this deletion:

```ts
import koffi from "koffi";

const user32 = koffi.load("user32.dll");

const GetForegroundWindow = user32.func("void *GetForegroundWindow()");
const GetWindowTextLengthW = user32.func("int GetWindowTextLengthW(void *hWnd)");
const GetWindowTextW = user32.func("int GetWindowTextW(void *hWnd, _Out_ char16_t *lpString, int nMaxCount)");

export function foregroundWindowTitle(): string {
  try {
    const hwnd = GetForegroundWindow();
    const length = GetWindowTextLengthW(hwnd);
    const buf = Buffer.alloc((length + 1) * 2);
    GetWindowTextW(hwnd, buf, length + 1);
    return koffi.decode(buf, "char16_t", length) || "?";
  } catch {
    return "?";
  }
}
```

- [ ] **Step 2: Wire the keyboard window into `main/index.ts`**

In `apps/desktop/src/main/index.ts`:

Remove the import on line 8:
```ts
import { toggleTouchKeyboard } from "./services/win32.service";
```

Add, next to the `createButtonsWindow` import (line 15):
```ts
import { createKeyboardWindow, showKeyboardWindow } from "./windows/keyboardWindow";
```

In the `BackendServer` construction (lines 60-66), replace:
```ts
    backend = new BackendServer({
      engine,
      config,
      configPath: "config.json",
      toggleTouchKeyboard,
      toggleVoiceTyping,
    });
```
with:
```ts
    backend = new BackendServer({
      engine,
      config,
      configPath: "config.json",
      openKeyboard: () => showKeyboardWindow(),
      toggleVoiceTyping,
    });
```

After the existing `createButtonsWindow(backend, saved.x, saved.y);` line (line 86), add:
```ts
    createKeyboardWindow(backend, config.custom_keyboard.x, config.custom_keyboard.y);
```

(`config` is already in scope from `loadConfig("config.json")` at the top of
this `app.whenReady()` callback, so no separate raw-JSON read is needed here
— unlike `readSavedButtonsPosition`, which predates this and is left as-is.)

- [ ] **Step 3: Update the Extras-tab hint copy**

In `apps/desktop/src/renderer/config/index.html`, the hint text under the
"Mostrar botão de teclado virtual" checkbox (lines 74-77) described the old
OS-toggle failure mode, which no longer applies. Replace:

```html
        <p class="hint">
          Em alguns PCs o teclado touch do Windows não está disponível e o botão
          nunca abre nada desative-o aqui pra tirá-lo da tela.
        </p>
```

with:

```html
        <p class="hint">
          Desative se você não usa o teclado virtual.
        </p>
```

- [ ] **Step 4: Full test suite, typecheck, and build**

Run: `pnpm --filter @facemesh-mouse/desktop test`
Expected: PASS, all tests.

Run: `pnpm --filter @facemesh-mouse/desktop run build`
Expected: succeeds (both `tsc -p tsconfig.json` and `tsc --noEmit -p tsconfig.renderer.json` pass, confirming no leftover reference to `toggleTouchKeyboard`/removed win32 exports anywhere).

- [ ] **Step 5: Manual smoke test**

Run: `pnpm --filter @facemesh-mouse/desktop run dev`

1. Click the ⌨ circle button — the keyboard panel appears bottom-center, above the taskbar.
2. Click into a text field in another app (e.g. Notepad, or a browser address bar) and click letters on the panel — verify each keystroke lands in that field, not in the panel itself, and that the panel never steals focus from it.
3. Click Shift, then a letter — verify uppercase; click Shift again — verify it goes back to lowercase without needing another letter click first.
4. Click an accented key (e.g. Ç) — verify it types correctly.
5. Click the "123" mode toggle — verify the numbers/punctuation rows appear/disappear; the panel does not resize or jump position.
6. Drag the panel by its top strip — verify it moves and the position persists after restarting the app.
7. Click ✕ — verify the panel hides; reopen via the ⌨ button — verify the last compact/full mode is still showing (it persists across restarts via config; shift is expected to reset to off on every fresh process start since it's intentionally not persisted).
8. In the config window's Extras tab, click "Redefinir posição do teclado/microfone" — verify both the circle buttons and the keyboard panel jump back to their default spots.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/main/index.ts apps/desktop/src/main/services/win32.service.ts apps/desktop/src/renderer/config/index.html
git commit -m "feat(keyboard): wire up the custom keyboard, remove the Windows touch-keyboard toggle"
```
