# FaceMesh Mouse — Electron Migration — Design Spec

**Date:** 2026-08-15
**Status:** Approved
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (v1),
`2026-08-05-usability-anchor-mode-design.md` (v2),
`2026-08-06-single-instance-background-startup-design.md` (v3),
`2026-08-07-gesture-expansion-modern-ui-design.md` (v4),
`2026-08-07-optical-flow-tracking-design.md` (v5),
`2026-08-07-mouse-yield-and-click-feedback-design.md` (v6),
`2026-08-13-virtual-keyboard-launcher-design.md` (v7),
`2026-08-13-floating-keyboard-button-design.md` (v8)

`2026-08-13-custom-onscreen-keyboard-design.md` (v9) is **not** part of this
chain: the working tree has since moved back to v7's native touch-keyboard
toggle, restructured `ui/keyboard_button.py` into `ui/action_buttons.py`
(now a keyboard **and** mic pair), and added `voice_typing.py`. That
evolution predates and is independent of this spec; this spec treats the
current source tree (not v9) as the baseline to migrate.

## Purpose

The app's tracking/gesture/mouse-control engine works well and is tuned
through six prior specs' worth of real usage; its UI (Tkinter +
CustomTkinter) is the part that feels dated. This spec replaces every
visual surface — config window, tray, click-feedback overlay, floating
keyboard/mic buttons — with an Electron + TypeScript frontend, while
keeping the entire tracking/gesture/mouse engine in Python, unchanged in
behavior. It is a **functional 1:1 port**: same tabs, same flow, same
gesture set, no new features. A visual redesign is an explicit later
phase (its own spec, likely using the `frontend-design` skill), once this
migration is working.

Rewriting the engine itself (optical-flow point tracking, the per-gesture
hold/cooldown state machine, mouse-yield-to-physical-touch, dwell click,
freeze/reanchor) in JavaScript was considered and rejected: none of that
logic is UI, all of it is tuned and tested, and the stated motivation for
this migration is the UI, not the engine.

## Architecture

Two processes:

- **Electron main process** — owns every window, the tray icon, global
  hotkeys, and single-instance enforcement. Spawns and owns the Python
  backend as a child process for the app's lifetime.
- **Python backend** — a new, headless entry point (`python -m
  facemesh_mouse.backend`) wrapping the existing `Engine`. No Tkinter, no
  CustomTkinter, no `pystray`, no `pynput` hotkey listener. Talks to
  Electron over its own stdin/stdout.

Renderer processes (the actual web pages) never talk to Python directly.
`nodeIntegration` stays off and `contextIsolation` stays on in every
`BrowserWindow`, matching Electron's standard security posture. The path
is:

```
Python stdout → Electron main (parses JSON lines) → webContents.send
  → preload contextBridge → renderer

renderer → preload contextBridge → ipcMain → Python stdin (child.stdin.write)
```

Electron main is the only process that reads/writes the child's stdio, so
it is the single source of truth for backend connection state and the
only place that needs to reason about partial lines / backpressure.

## Protocol

Newline-delimited JSON, one object per line. Python's `stdout` carries
**only** protocol messages; every `print()` currently used for
error/debug output in `engine.py`, `main.py`, `virtual_keyboard.py`,
`voice_typing.py`, and `action_buttons.py`'s save-position handler moves
to `stderr` (or a `logging` call configured to write there) as part of
this migration, since a stray stdout line would desync the protocol.

**Python → Electron (push):**

| type | fields | when |
|---|---|---|
| `frame` | `jpeg_b64`, `gesture_progress: {name: 0..1}`, `seq` | ~30fps, only while `set_preview` is enabled |
| `status` | `control_enabled`, `paused`, `no_face`, `yielded` | on any change |
| `action` | `gesture`, `action`, `x`, `y` | a gesture fired a mouse action (drives the click-feedback pulse; same moment `click_log.record` runs backend-side) |
| `keyboard_result` | `opened: bool`, `x`, `y` | reply to `open_keyboard`, see below |
| `error` | `message` | e.g. camera failed to open |

The preview frame carries a **pre-rendered** JPEG — the same nose-dot /
eye-line overlay `config_gui.py`'s `_render_preview` draws today via
`cv2.line`/`cv2.circle` stays in Python, drawn before encoding. Electron
never receives raw landmarks and never needs `tracker.py`'s landmark
indices ported to TypeScript.

`gesture_progress` is computed backend-side by calling the existing
`gestures.trigger_progress(name, metrics, threshold)` once per gesture
per frame — the same function `gesture_panel.py` calls today — so the
"which gestures are close to firing" logic isn't duplicated in
TypeScript either.

**Electron → Python (command):**

| type | fields | effect |
|---|---|---|
| `set_preview` | `enabled: bool` | starts/stops `frame` pushes — sent `true` only while the config window is visible, replacing today's `winfo_viewable()` gate in `config_gui.py`'s `_tick` |
| `start` / `stop` / `pause` / `resume` | — | mirrors `engine.control_enabled`/`engine.paused` |
| `update_config` | `config` | live-applies, equivalent to `engine.update_config` |
| `save_config` | `config` | persists to `config.json` |
| `open_keyboard` | `x`, `y` | calls `virtual_keyboard.open_virtual_keyboard()`; `x`/`y` are echoed back in `keyboard_result` so the overlay knows where to pulse |
| `open_voice_typing` | — | calls `voice_typing.toggle_voice_typing()`; fire-and-forget, no result message, since that function already returns nothing and always attempts the toggle |

### Config serialization

`config.py` already round-trips `AppConfig` through `dataclasses.asdict`
for file I/O (`save_config`) and a hand-written merge/clamp path for
reads (`load_config`). This spec extracts that into two explicit
functions — `config_to_dict(config) -> dict` (thin wrapper over
`asdict`) and `config_from_dict(raw: dict) -> AppConfig` (today's
validation/clamping/legacy-gesture-name logic in `load_config`, minus
the file read) — so `update_config`/`save_config` messages and disk I/O
share the exact same parsing path. `load_config`/`save_config` become
thin wrappers around these two functions plus the file read/write.
Without this, the IPC payload and the on-disk schema would validate
independently and could drift.

### Backpressure

Python only encodes and sends the next `frame` after the previous one has
flushed — a single frame in flight, never a growing queue, which throttles
naturally to whatever rate the Electron side can actually consume.

## Windows (Electron side)

| Window | Type | Replaces |
|---|---|---|
| Config | normal, show/hide, tabs Movimento/Gestos/Ajuda | `config_gui.py`, `calibration_panel.py`, `gesture_panel.py` |
| Click-feedback overlay | frameless, transparent, always-on-top, click-through (`setIgnoreMouseEvents(true, {forward: true})`), one persistent window sized to the full virtual desktop (spanning every display, via `screen.getPrimaryDisplay().workArea` bounds unioned across `screen.getAllDisplays()`) that animates at the pushed `x`/`y` on each `action`/`keyboard_result` | `click_feedback.py` (today spawns one `Toplevel` per pulse, positioned in absolute screen coordinates that already work across monitors) |
| Floating keyboard/mic buttons | frameless, transparent, always-on-top, draggable, **not** click-through | `action_buttons.py` |
| Tray | Electron `Tray`, icon swapped by state (idle/paused/no-face/yielded, same precedence order paused > yielded > no-face > running), menu Pausar-Retomar/Reabrir Config/Sair | `tray.py` (`pystray`) |

The floating buttons' screen position becomes Electron-owned: the
window's own drag handler (`mousedown`/`mousemove` in the renderer,
`BrowserWindow.setPosition`) tracks it directly, with no `update_config`
round-trip per pixel of drag — only on release does the final `x`/`y`
get folded into the next `save_config`/`update_config` payload's
`action_buttons` field. This mirrors today's split, where dragging never
touches disk and only an explicit save does.

## Hotkeys & single instance

`hotkeys.py` (`pynput.keyboard.GlobalHotKeys`) is deleted; Electron's
`globalShortcut.register('Ctrl+Alt+P', ...)` /
`globalShortcut.register('Ctrl+Alt+O', ...)` call the same two handlers
(toggle pause, show config window) that the tray menu and buttons use.

`single_instance.py` is deleted. It does two jobs today — refuse to start
a second copy, and signal the running copy to reopen its config window —
both of which `app.requestSingleInstanceLock()` plus Electron's
`second-instance` event cover natively. Since Electron is now the sole
entry point and owns exactly one Python child for its own lifetime, the
Python side needs no singleton logic of its own.

## Keyboard/voice feedback loop

`open_virtual_keyboard()` returns whether the touch keyboard actually
became visible — `False` most commonly means no editable field had
focus. Today `action_buttons.py` uses that bool to pick a green pulse
(opened) vs. a red warning pulse + tooltip ("Clique num campo de texto
antes de abrir o teclado"). That decision moves to the click-feedback
overlay renderer, driven by `keyboard_result.opened`: `true` → normal
pulse, `false` → warning pulse + tooltip, same text, same color
(`WARNING_PULSE_COLOR = #ff4d4d`).

`toggle_voice_typing()` has no success/failure signal to report today
(it sends Win+H and returns nothing) — `open_voice_typing` stays
fire-and-forget, and the renderer shows a normal pulse immediately on
click rather than waiting for a reply that will never come.

## Packaging

`electron-builder`, `nsis` target (Windows). The Python backend is frozen
to a standalone executable via `pyinstaller --onefile` — a new, much
smaller spec than today's `facemesh-mouse.spec`, since it drops
`tkinter`, `customtkinter`, `pystray`, and `pynput`'s hotkey/keyboard
pieces (still needs `pynput.keyboard.Controller` for voice typing) —
and included via `electron-builder`'s `extraResources`. The main process
resolves its path the same way `main.py`'s `_resource_path` does today:
`process.resourcesPath` in a packaged build, a relative dev path
(`python -m facemesh_mouse.backend`) otherwise. `assets/icon.ico` is
reused for the installer, the app windows, and the tray icon.

## Error handling

- Camera fails to open: backend sends `error` then exits; Electron shows
  a native `dialog.showErrorBox`, replacing today's `tk.messagebox`
  shown from `main.py`.
- Backend exits unexpectedly while running: Electron's `child.on('exit',
  ...)` fires a dialog offering restart or quit — new behavior; today
  this failure mode doesn't exist because engine and UI share a process.
- A malformed/partial JSON line on either side is logged (to stderr in
  Python, to the main process's console in Electron) and dropped, never
  thrown — the same "one bad frame must never kill tracking" philosophy
  `Engine._run`'s per-frame `try/except` already applies.
- On quit, Electron sends `stop`, closes stdin, and waits briefly for
  the child to exit before `SIGTERM`, mirroring `Engine.stop()`'s
  `thread.join(timeout=2)`.

## Testing

- **Backend**: `test_config.py`, `test_gestures.py`,
  `test_mouse_controller.py` and the tracker/point-tracker/click-log
  tests are pure logic and need no change beyond following
  `config_to_dict`/`config_from_dict`'s extraction. New
  `test_ipc_protocol.py` covers line framing and command dispatch
  (`start`/`stop`/`pause`/`resume`/`update_config`/`save_config`/
  `set_preview`/`open_keyboard`/`open_voice_typing`) against a fake
  stdin/stdout pair.
- **Removed**: `test_click_feedback.py`, `test_config_gui.py`,
  `test_gestures.py`'s panel-facing pieces (bar-progress logic itself
  moves with `trigger_progress`, which stays Python — only the
  CustomTkinter widget tests go), and any test touching
  `action_buttons.py`'s Tkinter construction — those modules move to
  TypeScript.
- **Electron/TypeScript**: unit tests for the main-process command
  handlers and the preload bridge; one handshake smoke test that spawns
  the real backend executable and asserts a first `status` message
  arrives within a timeout.
- **Manual**: full camera + gesture + click flow, as today — this
  project has never had automated coverage for that end-to-end path,
  and this migration doesn't add any.

## Out of scope (YAGNI)

- Visual redesign of any screen — this is a like-for-like port; a
  follow-up spec covers redesign once this one is working end-to-end.
- Cross-platform support (macOS/Linux) — the backend still uses
  Windows-only APIs (`ITipInvocation` COM, `SetProcessDpiAwareness`,
  `SystemParametersInfoW`) untouched by this spec.
- Auto-update — `electron-builder`'s NSIS target is configured for a
  plain installer, not an auto-update channel.
- Moving `trigger_progress`, `tracker.py`'s landmark math, or any other
  engine logic to TypeScript.
- Changing the gesture set, config schema fields, or default values.
