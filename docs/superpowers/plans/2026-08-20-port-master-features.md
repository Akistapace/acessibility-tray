# Port master's unmerged features into the Node port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port three features that exist only on `master` (built against the old `electron/`+Python architecture, after the `worktree-node-port` branch's config port already happened) into the completed, Python-free `apps/desktop` TypeScript codebase: (1) keyboard/voice floating-button visibility toggles, (2) hover-to-highlight gesture regions in the camera preview, (3) full cursor appearance customization (size/color/"mista" invert mode) via the real Windows cursor.

**Architecture:** All three slot into the existing `apps/desktop` structure with no new top-level folders: config fields go in `config.service.ts`, new IPC commands go through the existing `send()` dispatch in `backendServer.ts`, new native Windows calls follow `win32.service.ts`'s established koffi pattern (new sibling file, not additions to that file — cursor theme is a distinct concern), and UI goes in the existing Extras tab.

**Tech Stack:** TypeScript, koffi (already a dependency, used identically to `win32.service.ts`), no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-18-cursor-appearance-design.md` (feature 3's original design — written against the old Python+Electron architecture; this plan translates its architecture references but keeps its actual feature design — cursor modes, `.cur` byte layout, hotspot, error-swallowing rules — unchanged). Features 1 and 2 have no separate spec document; their design is captured directly in this plan from the reference Python/Electron diff (`git diff worktree-node-port...master`).

## Global Constraints

- Every new native/OS-integration call follows this project's established rule: a failure here must never crash tracking or the app — catch, log to stderr via `console.error`, degrade gracefully. Matches `win32.service.ts`'s `toggleTouchKeyboard`/`foregroundWindowTitle` and `mouseController.service.ts`'s `onAction` catches.
- `CursorConfig`'s `apply_cursor` no-op guard (`size_px === 32 && mode === "default"` → treat as "nothing to apply, restore if something was") is load-bearing: an existing user who never opens the cursor section must see zero behavior change, ever.
- Every value written to `config.json` must round-trip through `configToDict`/`configFromDict` exactly like existing fields (`calibration`, `action_buttons`) — same clamp/fallback pattern, same JSON shape.
- UI copy is Portuguese (pt-BR), matching every existing string in `apps/desktop/src/renderer/config/index.html`.
- No PIL/canvas/native-image dependency: the `.cur` bitmap is generated with a hand-rolled polygon rasterizer in pure TypeScript (see Task 3) — this keeps cursor generation synchronously callable from the main process (needed at startup, before any renderer window is guaranteed open) without an IPC round-trip to a renderer's canvas.
- Only the `Arrow` cursor role is ever touched, never any of Windows' other 16 cursor roles.

---

### Task 1: Keyboard/voice button visibility toggles

**Files:**
- Modify: `apps/desktop/src/main/services/config.service.ts` (add `keyboard_button_enabled`/`voice_button_enabled` to `CalibrationConfig`)
- Modify: `apps/desktop/tests/config.test.ts` (append)
- Create: `apps/desktop/src/renderer/buttons/buttonVisibility.ts`
- Create: `apps/desktop/tests/buttonVisibility.test.ts`
- Modify: `apps/desktop/src/renderer/buttons/index.ts` (apply visibility on config, request config on load)
- Modify: `apps/desktop/src/renderer/config/index.html` (Extras tab checkboxes)
- Modify: `apps/desktop/src/main/ipc/buttons.ipc.ts` or wherever `get_config`/`config` message flow already exists — no new IPC needed, this rides the existing `config` broadcast (see `backendServer.ts`'s `save_config` case, which already re-sends the full config after every save) and the buttons window's existing preload `backend` bridge (`window.backend.on("config", ...)`, matching the pattern the config renderer already uses).

**Interfaces:**
- Consumes: `AppConfig`/`CalibrationConfig` (this same task, Step 1).
- Produces: `isKeyboardButtonEnabled(config)`, `isVoiceButtonEnabled(config)` — pure functions consumed only by `buttons/index.ts`.

**Reference (from `git diff worktree-node-port...master -- src/facemesh_mouse/modules/config.py`):** `keyboard_button_enabled`/`voice_button_enabled`, both `boolean`, default `true`, same `typeof raw === "boolean"` fallback pattern every other boolean calibration field already uses in `configFromDict`.

- [ ] **Step 1: Add the two config fields**

In `apps/desktop/src/main/services/config.service.ts`:
```ts
export interface CalibrationConfig {
  sensitivity_x: number;
  sensitivity_y: number;
  acceleration: number;
  motion_threshold_px: number;
  yield_resume_after_s: number;
  click_logging_enabled: boolean;
  dwell_click_enabled: boolean;
  dwell_time_s: number;
  keyboard_button_enabled: boolean;
  voice_button_enabled: boolean;
}
```
In `defaultCalibration()`, add `keyboard_button_enabled: true, voice_button_enabled: true,`.

In `configFromDict`, alongside the existing `click_logging_enabled`/`dwell_click_enabled` boolean-fallback pattern:
```ts
  const keyboardButtonRaw = rawCal.keyboard_button_enabled;
  const keyboard_button_enabled = typeof keyboardButtonRaw === "boolean" ? keyboardButtonRaw : fallback.calibration.keyboard_button_enabled;

  const voiceButtonRaw = rawCal.voice_button_enabled;
  const voice_button_enabled = typeof voiceButtonRaw === "boolean" ? voiceButtonRaw : fallback.calibration.voice_button_enabled;
```
and add both to the returned `calibration` object.

- [ ] **Step 2: Write failing test (append to `apps/desktop/tests/config.test.ts`)**

Check the real current test file's style first (fixture-builder function name, assertion style) and match it. The test must cover: default is `true` for both fields; explicit `false` round-trips through `configToDict`/`configFromDict`; a non-boolean value (e.g. `"yes"`, `1`) falls back to the default per the existing fallback pattern.

- [ ] **Step 3: Run test, confirm it fails**

Run: `pnpm --filter @facemesh-mouse/desktop exec vitest run tests/config.test.ts`
Expected: FAIL — the new fields aren't read/written yet (or the test references properties that don't exist).

- [ ] **Step 4: Implement (Step 1's code above), run test, confirm it passes**

- [ ] **Step 5: Create `apps/desktop/src/renderer/buttons/buttonVisibility.ts`**

```ts
interface ConfigLike {
  calibration?: {
    keyboard_button_enabled?: boolean;
    voice_button_enabled?: boolean;
  };
}

// Absent config (nothing received yet) and an absent flag on a received
// config both mean "enabled" -- only an explicit false hides the button.
export function isKeyboardButtonEnabled(config: ConfigLike | null | undefined): boolean {
  return config?.calibration?.keyboard_button_enabled !== false;
}

export function isVoiceButtonEnabled(config: ConfigLike | null | undefined): boolean {
  return config?.calibration?.voice_button_enabled !== false;
}
```

- [ ] **Step 6: Write failing test (`apps/desktop/tests/buttonVisibility.test.ts`)**

Cover: `undefined`/`null` config → both `true`; config with no `calibration` key → both `true`; `calibration.keyboard_button_enabled: false` → keyboard `false`, voice unaffected; same for voice; both `true` explicitly → both `true`.

- [ ] **Step 7: Run test, confirm it fails, implement (already done in Step 5), confirm it passes**

- [ ] **Step 8: Wire into `apps/desktop/src/renderer/buttons/index.ts`**

Read the real current file first (it was ported in an earlier task from before this button-visibility feature existed — check its actual current shape, don't assume). Add:
```ts
import { isKeyboardButtonEnabled, isVoiceButtonEnabled } from "./buttonVisibility.js";
```
Add a `window.backend.on("config", (message) => { ... })` handler (matching the existing pattern in `apps/desktop/src/renderer/config/index.ts` for the same event) that reads `(message as { config: unknown }).config`, calls both visibility functions, and sets `keyboard.style.display` / `mic.style.display` to `""` or `"none"` on the existing keyboard/mic circle elements (their real element IDs/variable names are already in the file — check them, don't guess). At the end of the file (module load), send `window.backend.send({ type: "get_config" })` so the buttons window learns the current config on open (it doesn't otherwise request one).

- [ ] **Step 9: Add the Extras tab checkboxes**

In `apps/desktop/src/renderer/config/index.html`'s Extras tab section (create the tab if it doesn't exist yet in this branch's current file — check first; if the Extras tab already exists from an earlier task, add to it):
```html
<label>
  <input type="checkbox" id="keyboard_button_enabled" /> Mostrar botão de teclado virtual
</label>
<p class="hint">
  Em alguns PCs o teclado touch do Windows não está disponível e o botão
  nunca abre nada — desative-o aqui pra tirá-lo da tela.
</p>
<label>
  <input type="checkbox" id="voice_button_enabled" /> Mostrar botão de digitação por voz
</label>
<p class="hint">
  Desative se você não usa digitação por voz — o botão de microfone some
  da tela junto com o de teclado.
</p>
```
Check `apps/desktop/src/renderer/config/index.ts`'s `applyConfigToForm`/`readFormIntoConfig` (or equivalent current functions) — if they already iterate `Object.keys(currentConfig.calibration)` generically (matching pattern from other calibration fields), these two checkboxes need no additional JS wiring beyond existing in `currentConfig.calibration`'s default object literal (add `keyboard_button_enabled: true, voice_button_enabled: true,` there too, matching `config.service.ts`'s defaults).

- [ ] **Step 10: Full-suite check + manual verification note**

Run: `pnpm --filter @facemesh-mouse/desktop test`, both `tsc --noEmit` configs, `pnpm --filter @facemesh-mouse/desktop build`.
Manual verification (cannot be performed by an agent — no GUI/camera in this environment, matching this plan's established policy): toggle each checkbox, save, confirm the corresponding floating button appears/disappears without restarting the app.

- [ ] **Step 11: Commit**

```bash
git add apps/desktop/src/main/services/config.service.ts apps/desktop/tests/config.test.ts apps/desktop/src/renderer/buttons/buttonVisibility.ts apps/desktop/tests/buttonVisibility.test.ts apps/desktop/src/renderer/buttons/index.ts apps/desktop/src/renderer/config/index.html apps/desktop/src/renderer/config/index.ts
git commit -m "feat(ui): port keyboard/voice floating-button visibility toggles from master"
```

---

### Task 2: Hover-to-highlight gesture regions in the camera preview

**Files:**
- Modify: `apps/desktop/src/renderer/tracking/faceMetrics.ts` (add `GESTURE_LANDMARK_GROUPS`, or create a sibling constants file if that reads cleaner — implementer's call, but keep it colocated with the tracking renderer since it's landmark-index data, not a service concern)
- Modify: `apps/desktop/src/main/ipc/tracking.ipc.ts` or `apps/desktop/src/main/services/backendServer.ts` (whichever already owns per-frame/preview command handling — check current file structure; the `highlight_gesture` command is a `backendServer.send()` case, matching `set_preview`)
- Modify: `apps/desktop/src/renderer/tracking/index.ts` (draw the highlight ellipse in `renderPreviewJpeg`, from Task 16)
- Modify: `apps/desktop/src/renderer/config/index.ts` (gesture-row hover → send `highlight_gesture`)
- Modify: `apps/desktop/tests/faceMetrics.test.ts` (append, if `GESTURE_LANDMARK_GROUPS` warrants a test — it's static data, a light existence/shape check is enough, no need for elaborate tests)

**Interfaces:**
- Consumes: `EYE_A`/`EYE_B`/`EYEBROW_A`/`EYEBROW_B`/`EYELID_TOP_A`/`EYELID_TOP_B`/mouth landmark constants (already in `faceMetrics.ts` from Task 7 — check their real names, the brief's names below are from the Python reference and may differ slightly in the existing TS port).
- Produces: `GESTURE_LANDMARK_GROUPS: Record<string, number[]>`, consumed only by the tracking renderer's preview-overlay drawing.

**Important — this feature moved from main-process (Python) to renderer-process (TS) because Task 16 already relocated preview rendering into the tracking renderer.** In the Python reference, `backend.py` held `highlighted_gesture` state and `preview.py` (main-process, same process as the camera loop) drew the highlight. In this port, `renderPreviewJpeg` already runs in `apps/desktop/src/renderer/tracking/index.ts` (Task 16), not in main. So: main process still needs to track "which gesture is currently highlighted" (since the config window, a *different* renderer, is what sends the hover event) and forward it to the tracking renderer — the same `tracking:set-preview` pattern Task 13 already established for `previewEnabled`. Do not try to draw the highlight from the main process; there is no image data there to draw on.

- [ ] **Step 1: Add `GESTURE_LANDMARK_GROUPS` to the tracking renderer**

Read the real current `apps/desktop/src/renderer/tracking/faceMetrics.ts` first to get the exact landmark constant names in this port (they were ported in Task 7 from `tracker.py`; the Python reference below uses `tracker.py`'s names — map them to whatever this file actually calls them). Reference data (from `git diff worktree-node-port...master -- src/facemesh_mouse/modules/tracker.py`):
```ts
const MOUTH_LANDMARKS = [MOUTH_TOP_INNER, MOUTH_BOTTOM_INNER, MOUTH_CORNER_LEFT, MOUTH_CORNER_RIGHT]; // use this file's real mouth-landmark constant names

export const GESTURE_LANDMARK_GROUPS: Record<string, number[]> = {
  blink_a: EYE_A,
  blink_b: EYE_B,
  blink_both: [...EYE_A, ...EYE_B],
  eyebrow_a: [EYEBROW_A, EYELID_TOP_A, ...EYE_A],
  eyebrow_b: [EYEBROW_B, EYELID_TOP_B, ...EYE_B],
  eyebrow_both: [EYEBROW_A, EYELID_TOP_A, EYEBROW_B, EYELID_TOP_B, ...EYE_A, ...EYE_B],
  mouth_open: MOUTH_LANDMARKS,
  mouth_left: MOUTH_LANDMARKS,
  mouth_right: MOUTH_LANDMARKS,
};
```
(the mouth gestures share one landmark set — `mouth_left`/`mouth_right` are read off the same mouth-center-vs-face-axis measurement as `mouth_open`, not a distinct mouth region, matching the Python reference's own comment.)

- [ ] **Step 2: Wire `highlight_gesture` into `BackendServer`**

Add a `highlightedGesture: string | null = null` field and a `highlightListeners: Array<(gesture: string | null) => void> = []` array plus an `onHighlightChange` registration method — mirror `onPreviewChange`'s exact shape (same file, `backendServer.ts`). Add a `send()` case:
```ts
case "highlight_gesture": {
  const gesture = command.gesture as string | null;
  this.highlightedGesture = gesture && (GESTURE_NAMES as readonly string[]).includes(gesture) ? gesture : null;
  for (const listener of this.highlightListeners) listener(this.highlightedGesture);
  break;
}
```
(import `GESTURE_NAMES` from `./config.service`, already exported there.)

- [ ] **Step 3: Forward highlight state to the tracking renderer**

In `apps/desktop/src/main/windows/trackingWindow.ts`, alongside the existing `backend.onPreviewChange(...)` wiring (Task 13/final-review-fix-wave), add `backend.onHighlightChange((gesture) => { win.webContents.send("tracking:highlight-gesture", gesture); })`. Add a matching preload bridge method in `apps/desktop/src/preload/index.ts` (`onHighlightGesture`, same shape as `onSetPreview`) and a new `ipcRenderer` channel name `"tracking:highlight-gesture"`.

- [ ] **Step 4: Draw the highlight in the tracking renderer's preview overlay**

In `apps/desktop/src/renderer/tracking/index.ts`, register `window.tracking.onHighlightGesture((gesture) => { highlightedGesture = gesture; })` (a module-level variable, mirroring the existing `previewEnabled` pattern from Task 13). In `renderPreviewJpeg` (Task 16), after the existing eye-line/nose-dot overlay drawing, add:
```ts
if (metrics && highlightedGesture) {
  const indices = GESTURE_LANDMARK_GROUPS[highlightedGesture];
  if (indices?.length) {
    const xs = indices.map((i) => metrics.landmarks[i][0] * PREVIEW_WIDTH);
    const ys = indices.map((i) => metrics.landmarks[i][1] * PREVIEW_HEIGHT);
    const xMin = Math.min(...xs), xMax = Math.max(...xs);
    const yMin = Math.min(...ys), yMax = Math.max(...ys);
    const padX = Math.max((xMax - xMin) * 0.4, 10);
    const padY = Math.max((yMax - yMin) * 0.4, 10);
    const cx = (xMin + xMax) / 2, cy = (yMin + yMax) / 2;
    const rx = (xMax - xMin) / 2 + padX, ry = (yMax - yMin) / 2 + padY;
    previewCtx.save();
    previewCtx.globalAlpha = 0.35;
    previewCtx.fillStyle = "rgb(0, 255, 0)";
    previewCtx.beginPath();
    previewCtx.ellipse(cx, cy, rx, ry, 0, 0, 2 * Math.PI);
    previewCtx.fill();
    previewCtx.restore();
    previewCtx.strokeStyle = "rgb(0, 255, 0)";
    previewCtx.lineWidth = 2;
    previewCtx.beginPath();
    previewCtx.ellipse(cx, cy, rx, ry, 0, 0, 2 * Math.PI);
    previewCtx.stroke();
  }
}
```
(canvas `ellipse()` takes radii, not a bounding box — this is the browser-canvas equivalent of the Python reference's `cv2.ellipse` axes/center approach, not a literal transliteration; verify the padding/color constants above match the Python reference's `HIGHLIGHT_PADDING_FRACTION=0.4`, `HIGHLIGHT_PADDING_MIN_PX=10`, `HIGHLIGHT_FILL_ALPHA=0.35`, `HIGHLIGHT_COLOR_BGR=(0,255,0)` → `rgb(0,255,0)` in canvas's RGB order, which they do.)

- [ ] **Step 5: Wire the config window's gesture-row hover**

In `apps/desktop/src/renderer/config/index.ts`'s gesture-row rendering (check the real current function name — likely something like `renderGestureRows`), add on each row:
```ts
row.addEventListener("pointerenter", () => {
  window.backend.send({ type: "highlight_gesture", gesture: name });
});
row.addEventListener("pointerleave", () => {
  window.backend.send({ type: "highlight_gesture", gesture: null });
});
```
Also send `{ type: "highlight_gesture", gesture: null }` when switching away from the Gestos tab (check the existing tab-switch handler and add this there), so the highlight doesn't stay stuck on when the user navigates elsewhere.

- [ ] **Step 6: Full-suite check**

Run: `pnpm --filter @facemesh-mouse/desktop test`, both `tsc --noEmit` configs, `pnpm --filter @facemesh-mouse/desktop build`.
Manual verification (cannot be performed by an agent): hover a gesture row in the config window's Gestos tab, confirm the preview highlights the right face region; leave the row, confirm it clears.

- [ ] **Step 7: Commit**

```bash
git add apps/desktop/src/renderer/tracking/faceMetrics.ts apps/desktop/src/main/services/backendServer.ts apps/desktop/src/main/windows/trackingWindow.ts apps/desktop/src/preload/index.ts apps/desktop/src/renderer/tracking/index.ts apps/desktop/src/renderer/config/index.ts
git commit -m "feat(ui): port hover-to-highlight gesture regions in the camera preview from master"
```

---

### Task 3: `.cur` file generation (pure logic, no OS calls)

**Files:**
- Create: `apps/desktop/src/main/services/cursorImage.ts`
- Create: `apps/desktop/tests/cursorImage.test.ts`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces: `VALID_CURSOR_MODES`, `buildCurBytesColor(sizePx, fillRgb): Buffer`, `buildCurBytesMista(sizePx): Buffer` — consumed by `cursorTheme.service.ts` (Task 4).

This is a direct, careful port of `cursor_image.py` (read via `git show master:src/facemesh_mouse/modules/cursor_image.py` if you need the reference again — the controller already read it in full during planning; the algorithm below is transcribed from that reading). No PIL/canvas dependency: polygon fill and outline are both hand-rolled, since this needs to run synchronously in the main process (cursor theme is applied at app startup, before any renderer window is guaranteed to exist).

- [ ] **Step 1: Write failing tests (`apps/desktop/tests/cursorImage.test.ts`)**

Test the parts that have a checkable invariant without needing a golden-image comparison:
```ts
import { describe, expect, it } from "vitest";
import { buildCurBytesColor, buildCurBytesMista, VALID_CURSOR_MODES } from "../src/main/services/cursorImage";

describe("VALID_CURSOR_MODES", () => {
  it("has exactly the five documented modes", () => {
    expect([...VALID_CURSOR_MODES].sort()).toEqual(["black", "custom", "default", "mista", "white"]);
  });
});

describe("buildCurBytesColor", () => {
  it("produces a valid ICONDIR + one ICONDIRENTRY header", () => {
    const bytes = buildCurBytesColor(32, [255, 0, 0]);
    // ICONDIR: reserved=0 (u16), type=2 (u16, cursor), count=1 (u16)
    expect(bytes.readUInt16LE(0)).toBe(0);
    expect(bytes.readUInt16LE(2)).toBe(2);
    expect(bytes.readUInt16LE(4)).toBe(1);
    // ICONDIRENTRY (offset 6): width byte, height byte both == 32
    expect(bytes.readUInt8(6)).toBe(32);
    expect(bytes.readUInt8(7)).toBe(32);
    // hotspot fields (xHotspot u16, yHotspot u16 at offset 10, 12) are (0, 0) -- tip of the arrow
    expect(bytes.readUInt16LE(10)).toBe(0);
    expect(bytes.readUInt16LE(12)).toBe(0);
    // image data offset (u32 at offset 12+4=16... check exact ICONDIRENTRY layout below) points past the 6+16=22 byte header
    expect(bytes.readUInt32LE(18)).toBe(22);
  });

  it("uses 256 (encoded as 0) for a 256px cursor's width/height byte", () => {
    // the ICO/CUR format encodes 256 as byte value 0 -- only test this if
    // 256 is a realistic size for this feature (check CURSOR_SIZE_RANGE in
    // config.service.ts -- if the max is 96, this edge case may not be
    // reachable and this test can be dropped; use your judgment)
  });

  it("total byte length matches a 32bpp BGRA image plus a 1bpp AND mask, both padded to 4-byte rows", () => {
    const sizePx = 32;
    const bytes = buildCurBytesColor(sizePx, [0, 0, 0]);
    const bmiHeaderSize = 40;
    const colorTableSize = 0; // bit_count > 8, no palette
    const xorRowBytes = sizePx * 4; // 32bpp, already 4-byte aligned at width 32
    const andRowBytes = ((sizePx + 31) >> 5) * 4; // 1bpp, padded to 4-byte boundary
    const expectedImageDataSize = bmiHeaderSize + colorTableSize + xorRowBytes * sizePx + andRowBytes * sizePx;
    expect(bytes.length).toBe(6 + 16 + expectedImageDataSize);
  });
});

describe("buildCurBytesMista", () => {
  it("produces a 1bpp cursor (bit_count field == 1 in the BITMAPINFOHEADER)", () => {
    const bytes = buildCurBytesMista(32);
    // BITMAPINFOHEADER starts right after the 22-byte ICONDIR+ICONDIRENTRY
    // header; biBitCount is a u16 at offset 14 within that 40-byte header
    const biBitCountOffset = 22 + 14;
    expect(bytes.readUInt16LE(biBitCountOffset)).toBe(1);
  });

  it("total byte length matches two 1bpp masks (AND + XOR) plus an 8-byte 2-color palette", () => {
    const sizePx = 32;
    const bytes = buildCurBytesMista(sizePx);
    const bmiHeaderSize = 40;
    const colorTableSize = 8; // bit_count <= 8 requires a palette; 2 entries x 4 bytes
    const maskRowBytes = ((sizePx + 31) >> 5) * 4;
    const expectedImageDataSize = bmiHeaderSize + colorTableSize + maskRowBytes * sizePx * 2;
    expect(bytes.length).toBe(6 + 16 + expectedImageDataSize);
  });
});
```
Adjust exact byte offsets if your own read of the assembly logic (Step 3 below) disagrees with the above — these tests encode the *invariants* (header field values, total size arithmetic), not byte-for-byte golden output, precisely so a correct alternate implementation isn't penalized for differing in, say, which helper function computes what. Get the offsets right against your own implementation, not by fudging the implementation to match a possibly-miscounted test.

- [ ] **Step 2: Run tests, confirm they fail**

Run: `pnpm --filter @facemesh-mouse/desktop exec vitest run tests/cursorImage.test.ts`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Implement `apps/desktop/src/main/services/cursorImage.ts`**

```ts
// Pure cursor bitmap / .cur-file generation -- no filesystem, no registry,
// no native calls. Builds an arrow silhouette and serializes it into the
// classic (non-PNG) .cur container: ICONDIR + one ICONDIRENTRY + a combined
// XOR+AND legacy DIB image, the same layout every .cur file has used since
// Windows 3.1. Ported from cursor_image.py -- see
// docs/superpowers/specs/2026-08-18-cursor-appearance-design.md. No
// PIL/canvas dependency: this needs to run synchronously in the main
// process (cursor theme applies at startup, before any renderer window is
// guaranteed open), so polygon fill/outline are hand-rolled here instead of
// delegated to a renderer's 2D canvas.

export const VALID_CURSOR_MODES = new Set(["default", "white", "black", "custom", "mista"]);

// Arrow silhouette as a fraction of the bitmap's own side length, tip at the
// origin (top-left) -- the polygon's first vertex is always the cursor's
// hotspot. Identical to cursor_image.py's _ARROW_POINTS_FRACTION.
const ARROW_POINTS_FRACTION: Array<[number, number]> = [
  [0.0, 0.0], [0.0, 0.62], [0.18, 0.48],
  [0.29, 0.72], [0.4, 0.67], [0.29, 0.44], [0.5, 0.44],
];

function polygonPoints(sizePx: number): Array<[number, number]> {
  return ARROW_POINTS_FRACTION.map(([x, y]) => [x * sizePx, y * sizePx]);
}

// Point-in-polygon via the standard even-odd ray-casting test, evaluated at
// pixel centers (x+0.5, y+0.5) to match how rasterizers conventionally
// sample -- avoids the fill boundary being sensitive to exact-integer
// vertex coincidences.
function pointInPolygon(px: number, py: number, points: Array<[number, number]>): boolean {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i];
    const [xj, yj] = points[j];
    const intersects = yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

// Rasterizes the polygon's edges (not the fill) via a simple DDA line walk
// between consecutive vertices -- gives the 1px outline PIL's
// `ImageDraw.polygon(..., outline=...)` also draws, without needing a real
// stroking algorithm for this small, static 7-point shape.
function polygonEdgePixels(points: Array<[number, number]>, sizePx: number): Set<number> {
  const edgePixels = new Set<number>();
  const mark = (x: number, y: number) => {
    if (x >= 0 && x < sizePx && y >= 0 && y < sizePx) edgePixels.add(y * sizePx + x);
  };
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % points.length];
    const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0), 1);
    for (let s = 0; s <= steps; s++) {
      mark(Math.round(x0 + ((x1 - x0) * s) / steps), Math.round(y0 + ((y1 - y0) * s) / steps));
    }
  }
  return edgePixels;
}

function arrowMask(sizePx: number): Uint8Array {
  // 1 where inside the arrow silhouette, 0 outside -- pixel-center sampled.
  const points = polygonPoints(sizePx);
  const mask = new Uint8Array(sizePx * sizePx);
  for (let y = 0; y < sizePx; y++) {
    for (let x = 0; x < sizePx; x++) {
      if (pointInPolygon(x + 0.5, y + 0.5, points)) mask[y * sizePx + x] = 1;
    }
  }
  return mask;
}

function contrastOutlineColor(fill: [number, number, number]): [number, number, number] {
  const [r, g, b] = fill;
  const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
  return luminance > 127 ? [0, 0, 0] : [255, 255, 255];
}

// RGBA buffer (row-major, top-down, 4 bytes/pixel) -- fill inside the arrow
// silhouette, a 1px contrasting outline on the polygon edge, fully
// transparent outside.
function renderColorBitmap(sizePx: number, fill: [number, number, number]): Uint8Array {
  const mask = arrowMask(sizePx);
  const outline = contrastOutlineColor(fill);
  const edges = polygonEdgePixels(polygonPoints(sizePx), sizePx);
  const rgba = new Uint8Array(sizePx * sizePx * 4);
  for (let i = 0; i < sizePx * sizePx; i++) {
    const inside = mask[i] === 1;
    const onEdge = edges.has(i);
    const [r, g, b] = onEdge ? outline : fill;
    const alpha = inside || onEdge ? 255 : 0;
    rgba[i * 4] = r;
    rgba[i * 4 + 1] = g;
    rgba[i * 4 + 2] = b;
    rgba[i * 4 + 3] = alpha;
  }
  return rgba;
}

function packAndMask(sizePx: number, transparentAt: (x: number, y: number) => boolean): Buffer {
  return pack1bppRows(sizePx, transparentAt);
}

// bitIsSet(x, y) for a sizePx x sizePx grid. Returns bottom-up rows (DIB
// convention), each padded to a 4-byte boundary, MSB of each byte = the
// leftmost pixel of that byte's 8-pixel span.
function pack1bppRows(sizePx: number, bitIsSet: (x: number, y: number) => boolean): Buffer {
  const rowBytes = Math.ceil(sizePx / 32) * 4;
  const out = Buffer.alloc(rowBytes * sizePx);
  for (let y = sizePx - 1, outRow = 0; y >= 0; y--, outRow++) {
    for (let x = 0; x < sizePx; x++) {
      if (bitIsSet(x, y)) {
        const byteIndex = outRow * rowBytes + (x >> 3);
        out[byteIndex] |= 0x80 >> (x % 8);
      }
    }
  }
  return out;
}

// Bottom-up BGRA rows -- DIB byte order, not the RGBA buffer's own order.
function pack32bppRows(rgba: Uint8Array, sizePx: number): Buffer {
  const out = Buffer.alloc(sizePx * sizePx * 4);
  let outOffset = 0;
  for (let y = sizePx - 1; y >= 0; y--) {
    for (let x = 0; x < sizePx; x++) {
      const i = (y * sizePx + x) * 4;
      out[outOffset++] = rgba[i + 2]; // B
      out[outOffset++] = rgba[i + 1]; // G
      out[outOffset++] = rgba[i]; // R
      out[outOffset++] = rgba[i + 3]; // A
    }
  }
  return out;
}

function assembleCur(sizePx: number, bitCount: number, xorData: Buffer, andData: Buffer): Buffer {
  const bmi = Buffer.alloc(40);
  bmi.writeInt32LE(40, 0); // biSize
  bmi.writeInt32LE(sizePx, 4); // biWidth
  bmi.writeInt32LE(sizePx * 2, 8); // biHeight -- combined XOR + AND
  bmi.writeUInt16LE(1, 12); // biPlanes
  bmi.writeUInt16LE(bitCount, 14); // biBitCount
  bmi.writeUInt32LE(0, 16); // biCompression (BI_RGB)
  bmi.writeUInt32LE(xorData.length + andData.length, 20); // biSizeImage
  // biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant all 0, already zeroed by Buffer.alloc

  // DIB rule: bpp<=8 requires a palette (values irrelevant -- mask bits, not
  // palette indices, drive AND/XOR interpretation -- only presence matters).
  const colorTable = bitCount <= 8 ? Buffer.from([0, 0, 0, 0, 255, 255, 255, 0]) : Buffer.alloc(0);
  const imageData = Buffer.concat([bmi, colorTable, xorData, andData]);

  const icondir = Buffer.alloc(6);
  icondir.writeUInt16LE(0, 0); // reserved
  icondir.writeUInt16LE(2, 2); // type: 2 = cursor
  icondir.writeUInt16LE(1, 4); // count: 1 image

  const side = sizePx < 256 ? sizePx : 0; // 0 means 256 in the ICO/CUR format
  const icondirentry = Buffer.alloc(16);
  icondirentry.writeUInt8(side, 0); // width
  icondirentry.writeUInt8(side, 1); // height
  icondirentry.writeUInt8(0, 2); // color count (0 = no palette limit)
  icondirentry.writeUInt8(0, 3); // reserved
  icondirentry.writeUInt16LE(0, 4); // xHotspot
  icondirentry.writeUInt16LE(0, 6); // yHotspot -- both 0: tip of the arrow, matching ARROW_POINTS_FRACTION's first vertex
  icondirentry.writeUInt32LE(imageData.length, 8); // bytes in image data
  icondirentry.writeUInt32LE(6 + 16, 12); // offset: ICONDIR (6 bytes) + this one ICONDIRENTRY (16 bytes)

  return Buffer.concat([icondir, icondirentry, imageData]);
}

export function buildCurBytesColor(sizePx: number, fillRgb: [number, number, number]): Buffer {
  const rgba = renderColorBitmap(sizePx, fillRgb);
  const xorData = pack32bppRows(rgba, sizePx);
  const andData = packAndMask(sizePx, (x, y) => rgba[(y * sizePx + x) * 4 + 3] === 0);
  return assembleCur(sizePx, 32, xorData, andData);
}

// The classic invert-cursor trick: AND=1 everywhere (nothing is ever fully
// opaque-covered), XOR=1 only inside the arrow silhouette. Where AND=1,XOR=1
// the compositor inverts the destination pixel; where AND=1,XOR=0 it's
// untouched -- so the silhouette inverts the screen under it and everywhere
// else is fully see-through, with zero ongoing cost to this app.
export function buildCurBytesMista(sizePx: number): Buffer {
  const mask = arrowMask(sizePx);
  const andData = pack1bppRows(sizePx, () => true);
  const xorData = pack1bppRows(sizePx, (x, y) => mask[y * sizePx + x] === 1);
  return assembleCur(sizePx, 1, xorData, andData);
}
```

Double-check the ICONDIRENTRY byte offsets against your own test assertions from Step 1 as you implement — write the implementation first from this spec, then reconcile any offset mismatch between your test and implementation by re-deriving the correct offset from the ICO/CUR format (ICONDIR is 6 bytes: reserved u16, type u16, count u16; each ICONDIRENTRY is 16 bytes: width u8, height u8, colorCount u8, reserved u8, hotspotX u16, hotspotY u16, bytesInRes u32, imageOffset u32 — this is the authoritative layout, fix whichever of test/implementation disagrees with it).

- [ ] **Step 4: Run tests, confirm they pass**

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/main/services/cursorImage.ts apps/desktop/tests/cursorImage.test.ts
git commit -m "feat(modules): port cursor_image.py's .cur bitmap generation to TypeScript"
```

---

### Task 4: Cursor theme registry/API integration (koffi)

**Files:**
- Create: `apps/desktop/src/main/services/cursorTheme.service.ts`
- Create: `apps/desktop/tests/cursorTheme.test.ts`

**Interfaces:**
- Consumes: `buildCurBytesColor`/`buildCurBytesMista`/`VALID_CURSOR_MODES` (Task 3).
- Produces: `applyCursor(sizePx, mode, customColor): void`, `restoreCursor(): void` — consumed by `backendServer.ts` and `index.ts` (Task 5).

Follow `win32.service.ts`'s exact koffi conventions (same file already in this repo, read it again if needed): `koffi.load(...)`/`.func(...)` declarations at module scope, a `try/catch` wrapping every exported function with `console.error` on failure, `koffi.as(...)` for the `HKEY_CURRENT_USER` pseudo-handle. This module needs three more `advapi32.dll` functions beyond what `win32.service.ts` already declares (`RegQueryValueExW`, `RegDeleteValueW`) plus `user32.dll`'s `SystemParametersInfoW` — declare these locally in this new file rather than exporting them from `win32.service.ts`, since that file's own scope is touch-keyboard specifically (matches the project's one-concern-per-service-file convention).

- [ ] **Step 1: Write failing tests (`apps/desktop/tests/cursorTheme.test.ts`)**

This module's actual registry/API calls are OS-dependent and cannot be unit-tested (matching this project's established policy for `win32.service.ts`, `mouseController.service.ts`'s `NutJsMouseDriver` — manually verified, not unit-tested). What CAN be tested without mocking koffi: the no-op guard logic and the stash-file read/write logic, by extracting them into small pure-ish helper functions that take a filesystem path and don't touch the registry directly. Structure the module so:
```ts
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// Mock koffi entirely -- this test suite only verifies the stash/no-op
// logic, never real registry access.
vi.mock("koffi", () => ({
  default: {
    load: () => ({ func: () => vi.fn(() => 0) }),
    as: (v: unknown) => v,
  },
}));

describe("applyCursor no-op guard", () => {
  it("does nothing when size is default and mode is default, with no stash file present", async () => {
    const { applyCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "cursor-test-"));
    applyCursor(32, "default", "#000000", tmpDir);
    // No stash file should have been created -- nothing was ever "applied".
    expect(fs.existsSync(path.join(tmpDir, "original_arrow.json"))).toBe(false);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });
});

describe("restoreCursor without a prior apply", () => {
  it("is a pure no-op when no stash file exists", async () => {
    const { restoreCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "cursor-test-"));
    expect(() => restoreCursor(tmpDir)).not.toThrow();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });
});
```
This requires `applyCursor`/`restoreCursor` to accept an optional cursor-directory parameter (defaulting to the real `%LOCALAPPDATA%\FaceMeshMouse\cursors` path) purely so tests can inject a temp directory — mirrors how `clickLog.service.ts` or similar existing services structure their tests (check that file for the exact pattern this project already uses for path-injectable testing, and match it).

If, after reading the real koffi mock behavior, more of the stash-write/registry-write-attempt path can be exercised safely under the mock (e.g. confirming a stash file DOES get written on a real "apply" call, using the mocked no-op registry functions), add that too — but do not attempt to verify actual registry state or real `SystemParametersInfoW` calls; that's manual-verification territory, matching the design spec's own testing section.

- [ ] **Step 2: Run tests, confirm they fail**

- [ ] **Step 3: Implement `apps/desktop/src/main/services/cursorTheme.service.ts`**

Port `cursor_theme.py` directly (re-read it via `git show master:src/facemesh_mouse/cursor_theme.py` if needed — the controller's planning read is summarized here, but the implementer should verify against the real file for exact constant values):

```ts
import koffi from "koffi";
import fs from "node:fs";
import path from "node:path";
import { buildCurBytesColor, buildCurBytesMista, VALID_CURSOR_MODES } from "./cursorImage";

const user32 = koffi.load("user32.dll");
const advapi32 = koffi.load("advapi32.dll");

const SystemParametersInfoW = user32.func(
  "bool SystemParametersInfoW(uint32 uiAction, uint32 uiParam, void *pvParam, uint32 fWinIni)"
);
const RegCreateKeyExW = advapi32.func(
  "long RegCreateKeyExW(void *hKey, const char16_t *lpSubKey, uint32 Reserved, void *lpClass, uint32 dwOptions, uint32 samDesired, void *lpSecurityAttributes, _Out_ void **phkResult, void *lpdwDisposition)"
);
const RegQueryValueExW = advapi32.func(
  "long RegQueryValueExW(void *hKey, const char16_t *lpValueName, void *lpReserved, _Out_ uint32 *lpType, _Out_ uint8_t *lpData, _Inout_ uint32 *lpcbData)"
);
const RegSetValueExW = advapi32.func(
  "long RegSetValueExW(void *hKey, const char16_t *lpValueName, uint32 Reserved, uint32 dwType, const uint8_t *lpData, uint32 cbData)"
);
const RegDeleteValueW = advapi32.func("long RegDeleteValueW(void *hKey, const char16_t *lpValueName)");
const RegCloseKey = advapi32.func("long RegCloseKey(void *hKey)");

const HKEY_CURRENT_USER = koffi.as(0x80000001, "void *");
const CURSORS_KEY = "Control Panel\\Cursors";
const ARROW_VALUE = "Arrow";
const REG_SZ = 1;
const SPI_SETCURSORS = 0x0057;
const SPIF_SENDCHANGE = 0x0002;

const CUR_FILENAME = "arrow.cur";
const STASH_FILENAME = "original_arrow.json";
const DEFAULT_SIZE_PX = 32;
const MODE_COLORS: Record<string, [number, number, number]> = {
  default: [0, 0, 0],
  white: [255, 255, 255],
  black: [0, 0, 0],
};

function defaultCursorDir(): string {
  return path.join(process.env.LOCALAPPDATA ?? ".", "FaceMeshMouse", "cursors");
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace(/^#/, "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function readArrowRegistryValue(): string | null {
  const phkResult = [null];
  const rc = RegCreateKeyExW(HKEY_CURRENT_USER, CURSORS_KEY, 0, null, 0, 0x20019 /* KEY_READ|KEY_WRITE */, null, phkResult, null);
  if (rc !== 0) return null;
  try {
    const cbData = [520]; // MAX_PATH * 2 bytes, generous
    const buf = Buffer.alloc(cbData[0]);
    const type = [0];
    const readRc = RegQueryValueExW(phkResult[0], ARROW_VALUE, null, type, buf, cbData);
    if (readRc !== 0) return null;
    return koffi.decode(buf, "char16_t", cbData[0] / 2 - 1) || null;
  } finally {
    RegCloseKey(phkResult[0]);
  }
}

function writeArrowRegistry(value: string | null): void {
  const phkResult = [null];
  const rc = RegCreateKeyExW(HKEY_CURRENT_USER, CURSORS_KEY, 0, null, 0, 0x20006 /* KEY_WRITE */, null, phkResult, null);
  if (rc !== 0) return;
  try {
    if (value === null) {
      RegDeleteValueW(phkResult[0], ARROW_VALUE);
    } else {
      const buf = Buffer.from(value + "\0", "utf16le");
      RegSetValueExW(phkResult[0], ARROW_VALUE, 0, REG_SZ, buf, buf.length);
    }
  } finally {
    RegCloseKey(phkResult[0]);
  }
  SystemParametersInfoW(SPI_SETCURSORS, 0, null, SPIF_SENDCHANGE);
}

function stashOriginalIfNeeded(cursorDir: string): void {
  const stashPath = path.join(cursorDir, STASH_FILENAME);
  if (fs.existsSync(stashPath)) return;
  const value = readArrowRegistryValue();
  fs.mkdirSync(cursorDir, { recursive: true });
  fs.writeFileSync(stashPath, JSON.stringify({ value }), "utf-8");
}

export function applyCursor(sizePx: number, mode: string, customColor: string, cursorDir: string = defaultCursorDir()): void {
  if (sizePx === DEFAULT_SIZE_PX && mode === "default") {
    // Nothing was ever applied -> restoreCursor() is a pure no-op (no
    // registry read/write) because no stash file exists, so the
    // untouched-user guarantee is unchanged. Something WAS applied -> this
    // is an explicit revert to the Windows default, so put the original back.
    restoreCursor(cursorDir);
    return;
  }
  try {
    const effectiveMode = VALID_CURSOR_MODES.has(mode) ? mode : "default";
    const curBytes =
      effectiveMode === "mista"
        ? buildCurBytesMista(sizePx)
        : buildCurBytesColor(sizePx, effectiveMode === "custom" ? hexToRgb(customColor) : MODE_COLORS[effectiveMode]);

    stashOriginalIfNeeded(cursorDir);
    fs.mkdirSync(cursorDir, { recursive: true });
    const curPath = path.join(cursorDir, CUR_FILENAME);
    fs.writeFileSync(curPath, curBytes);
    writeArrowRegistry(curPath);
  } catch (exc) {
    console.error(`facemesh-mouse: cursor theme apply failed (${exc})`);
  }
}

export function restoreCursor(cursorDir: string = defaultCursorDir()): void {
  const stashPath = path.join(cursorDir, STASH_FILENAME);
  if (!fs.existsSync(stashPath)) return;
  try {
    const stash = JSON.parse(fs.readFileSync(stashPath, "utf-8"));
    writeArrowRegistry(stash.value ?? null);
    fs.unlinkSync(stashPath);
  } catch (exc) {
    console.error(`facemesh-mouse: cursor theme restore failed (${exc})`);
  }
}
```

Check `win32.service.ts`'s real `RegCreateKeyExW`/`RegSetValueExW` koffi signatures again before finalizing this file's declarations — reuse the exact same parameter-type spelling for consistency (this plan's snippet above should already match, but the implementer's read of the live file is the source of truth, not this plan).

- [ ] **Step 4: Run tests, confirm they pass**

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/main/services/cursorTheme.service.ts apps/desktop/tests/cursorTheme.test.ts
git commit -m "feat(modules): port cursor_theme.py's registry/SystemParametersInfoW integration to koffi"
```

---

### Task 5: Wire cursor theme into config, BackendServer, and startup/shutdown

**Files:**
- Modify: `apps/desktop/src/main/services/config.service.ts` (add `CursorConfig`)
- Modify: `apps/desktop/tests/config.test.ts` (append)
- Modify: `apps/desktop/src/main/services/backendServer.ts` (`set_cursor_theme` command, `save_config`'s cursor merge)
- Modify: `apps/desktop/tests/backendServer.test.ts` (append)
- Modify: `apps/desktop/src/main/index.ts` (startup apply, shutdown restore, camera-failure restore)

**Interfaces:**
- Consumes: `applyCursor`/`restoreCursor` (Task 4).
- Produces: `CursorConfig` on `AppConfig`, consumed by the Extras tab UI (Task 6).

- [ ] **Step 1: Add `CursorConfig` to `config.service.ts`**

```ts
export const CURSOR_SIZE_RANGE: [number, number] = [32, 96];
export const VALID_CURSOR_MODES = new Set(["default", "white", "black", "custom", "mista"]);

export interface CursorConfig {
  size_px: number;
  mode: string;
  custom_color: string;
}

function defaultCursor(): CursorConfig {
  return { size_px: 32, mode: "default", custom_color: "#000000" };
}

function clampedCursorSize(rawCursor: Record<string, unknown>, fallback: number): number {
  const [low, high] = CURSOR_SIZE_RANGE;
  const raw = rawCursor.size_px;
  const num = typeof raw === "number" || typeof raw === "string" ? Number(raw) : NaN;
  const resolved = Number.isFinite(num) ? Math.trunc(num) : fallback;
  return Math.max(low, Math.min(high, resolved));
}

// Exported (unlike the internal mergeGesture) because BackendServer's
// set_cursor_theme handler calls this directly with a single command's
// fields, not just from configFromDict's full-document parse -- both need
// the exact same clamp/fallback rules.
export function cursorFromDict(rawCursor: Record<string, unknown>): CursorConfig {
  const fallback = defaultCursor();
  const mode = typeof rawCursor.mode === "string" && VALID_CURSOR_MODES.has(rawCursor.mode) ? rawCursor.mode : fallback.mode;
  const customColor = typeof rawCursor.custom_color === "string" ? rawCursor.custom_color : fallback.custom_color;
  return { size_px: clampedCursorSize(rawCursor, fallback.size_px), mode, custom_color: customColor };
}
```
Add `cursor: CursorConfig` to the `AppConfig` interface, `cursor: defaultCursor()` to `defaultConfig()`'s return, and `cursor: cursorFromDict((raw.cursor as Record<string, unknown>) ?? {})` to `configFromDict`'s return. `configToDict` needs no change — it's already a generic `JSON.parse(JSON.stringify(config))`, which picks up `cursor` automatically once it's on the object.

- [ ] **Step 2: Test (append to `apps/desktop/tests/config.test.ts`)**

Cover: default `CursorConfig`; `size_px` clamps to `[32, 96]`; invalid `mode` falls back to `"default"`; `custom_color` round-trips as a string; a full `configFromDict`/`configToDict` round-trip includes `cursor`.

- [ ] **Step 3: Run tests, confirm pass**

- [ ] **Step 4: Add `set_cursor_theme` to `BackendServer`**

Import `applyCursor`/`restoreCursor` from `./cursorTheme.service` and `cursorFromDict` from `./config.service`. Add a `send()` case:
```ts
case "set_cursor_theme": {
  this.config.cursor = cursorFromDict({
    size_px: command.size_px,
    mode: command.mode,
    custom_color: command.custom_color,
  });
  applyCursor(this.config.cursor.size_px, this.config.cursor.mode, this.config.cursor.custom_color);
  break;
}
```
This does **not** write `config.json` — same "changes apply immediately, only Salvar persists them" split every other live-apply setting in this app already follows.

In `save_config`'s existing merge logic (alongside the `calibration`/`action_buttons` merge-if-present pattern), add:
```ts
if (payload.cursor) {
  merged.cursor = { ...(onDiskDict.cursor as object), ...(payload.cursor as object) };
}
```

- [ ] **Step 5: Test (append to `apps/desktop/tests/backendServer.test.ts`)**

Cover: `set_cursor_theme` updates `backendServer.config.cursor` and calls a spied/mocked `applyCursor` with the right arguments (mock `./cursorTheme.service` at the top of the test file, matching however this test file already mocks `./win32.service` for `toggleTouchKeyboard`, if it does — check the real file first); `save_config` merges a partial `cursor` payload against on-disk values, mirroring the existing `action_buttons` merge test.

- [ ] **Step 6: Run tests, confirm pass**

- [ ] **Step 7: Wire startup/shutdown into `index.ts`**

Read the real current `apps/desktop/src/main/index.ts` first. Add, right after `const config = loadConfig("config.json");`:
```ts
applyCursor(config.cursor.size_px, config.cursor.mode, config.cursor.custom_color);
```
(a saved cursor theme must survive an app restart, not just a live session — this call is unconditional, since `applyCursor` itself already no-ops correctly for the all-defaults case.)

In the `before-quit` handler (alongside the mouse-hold-release call from the final node-port review's fix wave), add `restoreCursor();`.

In the camera-open-failure path (the `dialog.showErrorBox(...)` + `app.quit()` block for the `"error"` message type), add `restoreCursor();` before `app.quit()` — a failed camera open still needs to hand the user's real cursor back, matching the Python reference's `main()`.

- [ ] **Step 8: Full-suite check**

Run: `pnpm --filter @facemesh-mouse/desktop test`, both `tsc --noEmit` configs, `pnpm --filter @facemesh-mouse/desktop build`.

- [ ] **Step 9: Commit**

```bash
git add apps/desktop/src/main/services/config.service.ts apps/desktop/tests/config.test.ts apps/desktop/src/main/services/backendServer.ts apps/desktop/tests/backendServer.test.ts apps/desktop/src/main/index.ts
git commit -m "feat(modules): wire cursor theme into config, BackendServer, and app startup/shutdown"
```

---

### Task 6: Cursor appearance Extras tab UI

**Files:**
- Modify: `apps/desktop/src/renderer/config/index.html`
- Modify: `apps/desktop/src/renderer/config/index.ts`

**Interfaces:**
- Consumes: `CursorConfig` shape (Task 5) via the existing `config` message / `currentConfig` object.
- Produces: nothing consumed elsewhere — this is the leaf UI.

- [ ] **Step 1: Add the Extras tab controls**

In `apps/desktop/src/renderer/config/index.html`'s Extras tab (below the keyboard/voice toggles from Task 1):
```html
<div class="cursor-section">
  <p class="hint">Aparência do cursor</p>
  <label>Tamanho da seta
    <input type="range" id="cursor_size_px" min="32" max="96" step="8" />
  </label>
  <label>Cor
    <select id="cursor_mode">
      <option value="default">Padrão do Windows</option>
      <option value="white">Branco</option>
      <option value="black">Preto</option>
      <option value="custom">Personalizada</option>
      <option value="mista">Mista (inverte com o fundo)</option>
    </select>
  </label>
  <label>Cor personalizada
    <input type="color" id="cursor_custom_color" />
  </label>
</div>
```

- [ ] **Step 2: Wire into `index.ts`**

Read the real current file first. `currentConfig`'s default object literal needs a `cursor: { size_px: 32, mode: "default", custom_color: "#000000" }` field. Unlike `calibration` fields (which the existing generic `Object.keys(currentConfig.calibration)` loop already handles) and unlike `action_buttons` (explicitly excluded from save payloads since another window owns it), `cursor` needs its own small explicit read/write block in `applyConfigToForm`/`readFormIntoConfig` (or equivalent current function names) since it's a top-level `AppConfigJson` key, not nested under `calibration`:
```ts
// in applyConfigToForm:
(document.getElementById("cursor_size_px") as HTMLInputElement).value = String(currentConfig.cursor.size_px);
(document.getElementById("cursor_mode") as HTMLSelectElement).value = currentConfig.cursor.mode;
(document.getElementById("cursor_custom_color") as HTMLInputElement).value = currentConfig.cursor.custom_color;

// in readFormIntoConfig:
currentConfig.cursor = {
  size_px: Number((document.getElementById("cursor_size_px") as HTMLInputElement).value),
  mode: (document.getElementById("cursor_mode") as HTMLSelectElement).value,
  custom_color: (document.getElementById("cursor_custom_color") as HTMLInputElement).value,
};
```
Unlike `action_buttons`, `cursor` IS included in `save_config`'s payload (this window is the sole owner of cursor settings) — check whatever function currently strips `action_buttons` from the save payload (e.g. `configPayloadWithoutButtons`) and confirm `cursor` is NOT stripped by it.

Add a live-apply listener, debounced ~150ms so dragging the size slider or picking a color doesn't flicker the real system cursor by regenerating/broadcasting dozens of times a second:
```ts
let cursorApplyTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleCursorApply(): void {
  if (cursorApplyTimer) clearTimeout(cursorApplyTimer);
  cursorApplyTimer = setTimeout(() => {
    readFormIntoConfig();
    window.backend.send({ type: "set_cursor_theme", ...currentConfig.cursor });
  }, 150);
}
for (const id of ["cursor_size_px", "cursor_mode", "cursor_custom_color"]) {
  document.getElementById(id)?.addEventListener("input", scheduleCursorApply);
}
```

- [ ] **Step 3: Full-suite check**

Run: `pnpm --filter @facemesh-mouse/desktop test`, both `tsc --noEmit` configs, `pnpm --filter @facemesh-mouse/desktop build`.
Manual verification (cannot be performed by an agent): drag the size slider — real Windows arrow visibly grows/shrinks. Pick white/black/custom — arrow recolors. Pick "Mista" — arrow inverts whatever's under it. Close the app (window close and tray "Sair") — Windows arrow returns to whatever it was before. Restart the app after saving a theme — themed arrow reappears automatically.

- [ ] **Step 4: Commit**

```bash
git add apps/desktop/src/renderer/config/index.html apps/desktop/src/renderer/config/index.ts
git commit -m "feat(ui): add cursor appearance controls to the Extras tab"
```

---

### Task 7: Final verification and README note

**Files:**
- Modify: `README.md` (Extras section — add cursor appearance to the feature list, matching how it's already described on `master`)

**Interfaces:** none.

- [ ] **Step 1: Update README's Extras description**

Check `master`'s README wording (`git show master:README.md`) for the cursor-appearance bullet and adapt it into this branch's already-rewritten (Node-only) README's Extras section, alongside the existing keyboard/voice/click-logging bullets from Task 1.

- [ ] **Step 2: Full-repo verification**

```bash
pnpm --filter @facemesh-mouse/desktop test
pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.json
pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.renderer.json
pnpm --filter @facemesh-mouse/desktop build
git status
```
Expected: all green, clean tree.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: describe the ported keyboard/voice/highlight/cursor Extras features"
```

---

## Plan Self-Review

**Spec coverage:** Feature 1 (keyboard/voice toggles) → Task 1. Feature 2 (gesture highlight) → Task 2. Feature 3 (cursor appearance) → Tasks 3-6, matching every section of `2026-08-18-cursor-appearance-design.md` (`cursor_theme.py` → Task 4, `config.py` → Task 5, backend wiring → Task 5, config UI → Task 6, error handling → both Tasks 4/5's try/catch blocks, testing → each task's own test steps, out-of-scope items — no task attempts any of them, confirmed absent by construction).

**Placeholder scan:** no TODOs. The one intentional forward-reference (Task 2 depends on Task 1 existing first for the Extras tab structure, and Tasks 4-6 depend on Task 3's `cursorImage.ts` existing) is ordering, not a placeholder — each task's file list is concrete and complete.

**Type consistency:** `CursorConfig` (Task 5) is used identically by `cursorTheme.service.ts` (Task 4, consumed via its exported functions' parameters, not the type itself — that module stays framework-agnostic on purpose) and the renderer (Task 6). `GESTURE_LANDMARK_GROUPS` (Task 2) keys are checked against `GESTURE_NAMES` implicitly by covering all nine gesture names. `buildCurBytesColor`/`buildCurBytesMista`'s signatures (Task 3) match exactly how `cursorTheme.service.ts` (Task 4) calls them.
