# FaceMesh Mouse — Custom On-Screen Keyboard (Electron port) — Design Spec

**Date:** 2026-08-23
**Status:** Approved
**Builds on:** `2026-08-13-custom-onscreen-keyboard-design.md` (Approved, written for the
Python/Tkinter app, never implemented — the Electron migration reintroduced the
Windows-touch-keyboard toggle instead). This spec ports that design to the current
Electron/TypeScript codebase and updates a few decisions.

## Purpose

The floating keyboard button (`⌨` circle in `apps/desktop/src/renderer/buttons`)
currently calls `toggleTouchKeyboard()` (`apps/desktop/src/main/services/win32.service.ts`),
which drives Windows' built-in touch keyboard through the undocumented
`ITipInvocation::Toggle()` COM interface. This is unreliable in exactly the way the
2026-08-13 spec already diagnosed:

- Windows only renders the touch keyboard when the foreground app has a focused
  editable control its legacy heuristic recognizes. `Toggle()` returns success even
  when it doesn't — there is no error to catch.
- That heuristic frequently fails to recognize modern web/Electron-rendered text
  fields, which is exactly what this app's users need to type into.
- The failure is silent; `backendServer.ts` currently compensates by polling
  `IsWindowVisible` for up to 400ms and reporting `opened: false`, which
  `overlay/index.ts` turns into a red warning pulse + tooltip.

This app's whole purpose is letting users who can't reliably use a physical
keyboard interact via head-tracked cursor clicks. A keyboard that silently
refuses to appear defeats that purpose. Building a small on-screen keyboard
directly into the app removes the dependency on Windows' text-field detection
entirely: every key sends a synthetic keystroke via nut-js — the same
mechanism `keyboard.service.ts`'s `toggleVoiceTyping` already uses for
Win+H — which every focused field receives identically to a real key press,
regardless of how that field is implemented.

## Decisions carried over from the 2026-08-13 spec

- Shift is a toggle, not a hold (a head-tracked-cursor click can't hold a key).
- Key press → synthetic input, not OS-level key events routed through a
  virtual HID driver.
- No Ctrl/Alt/Win/function/arrow/Tab/Esc keys, no autocomplete, one fixed
  QWERTY-based layout, no user-resizing of the panel.

## Decisions specific to this port

- **The custom keyboard fully replaces the Windows touch keyboard** — no
  toggle between the two. `win32.service.ts`'s COM/registry code is deleted.
- **Portuguese accented characters are included**: a dedicated row —
  `Á Ã Â À É Ê Í Ó Ô Õ Ú Ç` — always visible in both compact and full mode.
  nut-js's `keyboard.type()` sends unicode directly (confirmed by its existing
  use in `toggleVoiceTyping`), so each accented character is just another
  literal string, no dead-key composition needed.
- **No navigation keys** (Tab/arrows/Esc) — text entry only, same as the
  2026-08-13 scope decision.
- **No resize on compact/full toggle** — the window is sized once for the
  "full" layout (the tallest case); toggling to compact simply doesn't render
  the extra rows, leaving transparent space below. This avoids resizing an
  `alwaysOnTop` window mid-session (position jumps, and a saved x/y that no
  longer fits after a resize needs its own edge-case handling) for a purely
  cosmetic gap.

## Approach

### `main/windows/keyboardWindow.ts` (new)

Mirrors `buttonsWindow.ts`'s shape:

```ts
export function createKeyboardWindow(backend: BackendServer, savedX, savedY, compact): BrowserWindow
export function showKeyboardWindow(): void   // deiconify-equivalent: win.show() + win.moveTop(); no-op is fine if already visible
export function hideKeyboardWindow(): void   // win.hide(), called by the panel's own close button
export function moveKeyboardWindow(dx, dy): void      // same delta-accumulation pattern as moveButtonsWindow
export function endKeyboardDrag(): void                // persists x/y via save_config, same as endButtonsDrag
export function resetKeyboardPosition(): void
```

`BrowserWindow` options: `frame:false`, `transparent:true`, `alwaysOnTop:true`,
`skipTaskbar:true`, `resizable:false`, `focusable:false` — the same
`focusable:false` that already makes `buttonsWindow.ts` immune to stealing
focus from the real text field on click. No `WS_EX_NOACTIVATE` hack needed;
Electron already gives us the exact primitive the old Tkinter design had to
reach into Win32 for.

Created once in `main/index.ts` at startup (alongside `createButtonsWindow`),
starting hidden (`win.hide()`, not `showInactive()`). Because the window is
never destroyed, its renderer JS keeps running while hidden — shift state and
compact/full mode persist across opens for free, no extra bookkeeping needed
(this is actually simpler than the Tkinter version, which had to rely on
`winfo_viewable()` bookkeeping to get the same property).

**Open/close semantics:** `showKeyboardWindow()` only opens (idempotent if
already visible) — matches the button's existing one-directional intent.
Closing is exclusively the panel's own × button in its top strip, which sends
`keyboard:close`.

### `main/windows/keyboardPosition.ts` (new)

Same shape as `buttonsPosition.ts`: `WIDTH`/`HEIGHT` constants sized for the
full layout, `defaultPosition(screenW, screenH, taskbarReservedPx)` (bottom-
center, above the taskbar), `resolvePosition(savedX, savedY, screenW, screenH,
taskbarReservedPx)` with the same off-screen fallback-to-default guard.

### `renderer/keyboard/layout.ts` (new, pure data — directly unit-testable)

```ts
export const LETTER_ROWS = [
  [..."QWERTYUIOP"],
  [..."ASDFGHJKL"],
  [..."ZXCVBNM"],
];
export const ACCENT_ROW = [..."ÁÃÂÀÉÊÍÓÔÕÚ", "Ç"];
export const FULL_EXTRA_ROWS = [
  [..."1234567890"],
  [",", ".", "-", "?"],
];
```

`compact` renders `LETTER_ROWS` + `ACCENT_ROW` + the bottom row. `full`
additionally renders `FULL_EXTRA_ROWS` above the letter grid. `ACCENT_ROW` is
visible in both modes — Portuguese text needs it too often to gate behind
"full".

```ts
export function keyOutput(char: string, shiftActive: boolean): string
```

Pure function: uppercases when `shiftActive`, used by both the renderer (key
click handler) and its own unit tests.

### `renderer/keyboard/index.ts` + `index.html` + `style.css` (new)

Structural sibling of `renderer/buttons`: a drag-handle strip at the top
(same press/move/threshold pattern as `buttons/index.ts`'s `onHandlePointerDown`
/`onHandlePointerMove`/`onHandlePointerUp`, sending `keyboard:drag-move` /
`keyboard:drag-end`) plus, in the same strip, a compact/full toggle button and
a × close button (sends `keyboard:close`).

Keys are laid out with CSS grid, ~46px square (mirrors the old spec's
reasoning: the largest comfortable target is the easiest to hit with a
head-tracked, not pixel-precise, cursor); the Space key spans multiple
columns as the most-used key.

Key click handler:
- Letter/number/punctuation/accent keys: `window.backend.send({ type: "keyboard:type", text: keyOutput(char, shiftActive) })`.
- Shift: toggles local `shiftActive`, flips the key's own active/inactive
  styling. Does not auto-release after one letter.
- Backspace: `keyboard:backspace`. Enter: `keyboard:enter`.
- Space: `keyboard:type` with `text: " "`.

`window.backend.on("config", ...)` reads `custom_keyboard.compact` on load to
restore the last layout mode, same pattern `buttons/index.ts` already uses for
`keyboard_button_enabled`/`voice_button_enabled`.

### `main/services/keyboard.service.ts` (extend)

Add alongside the existing `toggleVoiceTyping`:

```ts
export async function typeText(text: string): Promise<void> {
  const { keyboard } = await import("@nut-tree-fork/nut-js");
  await keyboard.type(text);
}
export async function pressBackspace(): Promise<void> {
  const { keyboard, Key } = await import("@nut-tree-fork/nut-js");
  await keyboard.pressKey(Key.Backspace);
  await keyboard.releaseKey(Key.Backspace);
}
export async function pressEnter(): Promise<void> {
  const { keyboard, Key } = await import("@nut-tree-fork/nut-js");
  await keyboard.pressKey(Key.Enter);
  await keyboard.releaseKey(Key.Enter);
}
```

Each wrapped in try/catch + `console.error`, matching `toggleVoiceTyping`'s
existing failure handling — a dropped keystroke must never crash the app.

### `main/ipc/keyboard.ipc.ts` (new)

Registered from `ipc/index.ts` next to `registerButtonsIpc`. Listens on
`mainRelay` (colon-prefixed channels bypass `backendServer`, same as
`buttons:*` today):

```ts
mainRelay.on("keyboard:type", (msg: { text: string }) => typeText(msg.text));
mainRelay.on("keyboard:backspace", () => pressBackspace());
mainRelay.on("keyboard:enter", () => pressEnter());
mainRelay.on("keyboard:drag-move", (msg: { dx: number; dy: number }) => moveKeyboardWindow(msg.dx, msg.dy));
mainRelay.on("keyboard:drag-end", () => endKeyboardDrag());
mainRelay.on("keyboard:close", () => hideKeyboardWindow());
```

### `main/services/backendServer.ts` changes

`toggleTouchKeyboard?: () => Promise<boolean>` dep is replaced with
`openKeyboard?: () => void` (synchronous — no more visibility polling, since
the custom window can't silently fail to show). The `open_keyboard` case
becomes:

```ts
case "open_keyboard": {
  const x = Number(command.x ?? 0);
  const y = Number(command.y ?? 0);
  this.openKeyboardImpl();
  this.emit("message", { type: "keyboard_result", opened: true, x, y });
  break;
}
```

`keyboard_result` keeps its wire shape (the overlay still needs `x`/`y` to
place the pulse) but `opened` is now always `true`.

### `renderer/overlay/index.ts` changes

`keyboard_result` handler collapses to the same unconditional
`drawPulse(x, y, RING_COLOR)` the `action` handler already uses — the
`WARNING_COLOR`/`showTooltip` branch is deleted, since the custom keyboard
cannot fail to open the way the OS toggle could. If nothing else ends up
using `WARNING_COLOR`/`showTooltip` after this change, remove them from
`pulse.ts`/`overlay/index.ts` too.

### `main/services/win32.service.ts` changes

Delete everything touch-keyboard-specific: `toggleTouchKeyboard`,
`preferFloatingLayout`, `touchKeyboardVisible`, `guidBuffer`, `sleep`, and the
constants/bindings only they use (`CLSID_UI_HOST_NO_LAUNCH`,
`IID_ITIP_INVOCATION`, `CLSCTX_ALL`, `COINIT_APARTMENTTHREADED`, `S_OK`,
`S_FALSE`, `HKEY_CURRENT_USER`, `TABLET_TIP_KEY`, `EDGE_TARGET_DOCKED_STATE`,
`REG_DWORD`, `DOCKED_STATE_FLOATING`, `TOUCH_KEYBOARD_WINDOW_CLASS`,
`VISIBILITY_POLL_*`, the `ole32`/`advapi32` `koffi.load()` calls and every
`.func()` binding that only feeds those — `CoInitializeEx`, `CoUninitialize`,
`CLSIDFromString`, `CoCreateInstance`, `RegCreateKeyExW`, `RegSetValueExW`,
`RegCloseKey`, `FindWindowW`, `IsWindowVisible`). What remains: the `user32`
load and `foregroundWindowTitle()` (still used by `clickLog.service.ts`).

### `main/index.ts` changes

Remove the `toggleTouchKeyboard` import and its wiring into
`BackendServer`'s deps. Add `createKeyboardWindow(backend, saved.x, saved.y,
saved.compact)` next to `createButtonsWindow`, reading the saved position the
same way `readSavedButtonsPosition` does today (a small
`readSavedKeyboardPosition` helper, or generalize the existing one — either
is fine, implementer's call). Pass `openKeyboard: () => showKeyboardWindow()`
into `BackendServer`'s deps.

### `main/services/config.service.ts` changes

```ts
export interface CustomKeyboardConfig {
  x: number | null;
  y: number | null;
  compact: boolean;
}
```

Wired into `AppConfig`, `defaultConfig` (`{ x: null, y: null, compact: true }`),
and `configFromDict` exactly like `action_buttons` (reusing `optionalFloat`
for x/y, plain `typeof === "boolean"` fallback-to-default for `compact`), new
`"custom_keyboard"` JSON key. `save_config`'s merge logic in
`backendServer.ts` gets a `payload.custom_keyboard` branch alongside its
existing `action_buttons`/`cursor` ones.

### `renderer/config/index.html` copy change

The Extras-tab hint under "Mostrar botão de teclado virtual" currently reads:

> "Em alguns PCs o teclado touch do Windows não está disponível e o botão
> nunca abre nada — desative-o aqui pra tirá-lo da tela."

That warning described the old OS-toggle failure mode and no longer applies
(the custom keyboard always opens). Replace with a plain "desative se você
não usa o teclado virtual" — matching the mic button's existing hint style.

## Testing

- **`tests/keyboardLayout.test.ts`** — compact mode renders exactly
  `LETTER_ROWS` + `ACCENT_ROW` + bottom row; full mode additionally includes
  `FULL_EXTRA_ROWS`. `keyOutput` uppercases only when `shiftActive`.
- **`tests/keyboard.service.test.ts`** — `typeText`/`pressBackspace`/
  `pressEnter` call the mocked nut-js `keyboard` with the right
  args/key, following the existing `toggleVoiceTyping` mocking pattern (no
  dedicated test file exists for `keyboard.service.ts` today — this is new).
- **`tests/keyboardPosition.test.ts`** — mirrors `tests/position.test.ts`:
  default bottom-center placement, taskbar offset, saved-position clamping
  and off-screen fallback.
- **`tests/backendServer.test.ts`** — update "open_keyboard reports
  keyboard_result" to inject `openKeyboard: () => { called = true }` instead
  of `toggleTouchKeyboard`, assert `keyboard_result` is always `{ opened:
  true, x, y }` and that `openKeyboard` was called.
- **`tests/config.test.ts`** — `custom_keyboard` round-trips through
  `loadConfig`/`saveConfig`/`configFromDict`, same shape as the existing
  `action_buttons` coverage.
- Any existing `win32.service.ts` touch-keyboard tests (COM mocking, registry
  writes) are deleted along with the code they cover.

## Out of Scope (YAGNI)

- Ctrl/Alt/Windows/function keys, arrow keys, Tab, Esc.
- Autocomplete, word suggestions, predictive text.
- Multiple keyboard layouts (non-QWERTY, layouts for other languages).
- Resizing the panel, or resizing it automatically on compact/full toggle.
- Keeping the Windows touch keyboard as a fallback or alternate option.
- Any change to `voice_typing`/`toggleVoiceTyping` (already reliable — it
  also uses synthetic input, not an OS heuristic), or to `trackingEngine`,
  `mouseController`, `gestures`, `cursorTheme`.
