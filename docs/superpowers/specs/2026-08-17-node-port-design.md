# FaceMesh Mouse — Node Port — Design Spec

**Date:** 2026-08-17
**Status:** Draft
**Builds on:** `2026-08-15-electron-migration-design.md` (Electron frontend +
Python backend, two processes over stdio JSON)

## Purpose

The Electron migration replaced every Tkinter surface with Electron/TS but
kept the tracking/gesture/mouse engine in Python, talking to Electron over
a stdio newline-JSON protocol. This spec removes Python entirely: camera
capture, face-landmark tracking, optical-flow point tracking, gesture
detection, mouse control, config, and click-log all move to
TypeScript/Node, running inside the same Electron process tree. It also
flattens the repo — `electron/` stops being a nested sub-project and
becomes the repo root — and reorganizes the source tree into `src/modules`
(main-process logic) and `src/ui` (everything that runs in a renderer).

This is a **functional 1:1 port** of the engine, same as the Electron
migration was for the UI: same gesture set, same cursor math, same
config schema, no new features. It removes `run.py`, `src/facemesh_mouse/`,
`requirements*.txt`, `pyproject.toml`, `backend.spec`, the `.venv`, and
every Python test.

## Architecture

Still Electron, but one process tree instead of two:

- **Main process (Node)** — owns every window, the tray, global hotkeys,
  single-instance enforcement (all unchanged from the Electron migration),
  plus the engine: gesture evaluation, mouse control, config, click-log.
  This is the direct successor to `backend.py`/`engine.py`/`gestures.py`/
  `mouse_controller.py`.
- **Tracking renderer** — a hidden, always-alive `BrowserWindow` (created
  once at startup, independent of the config window's visibility, for the
  same reason `SharedState` avoided two consumers opening the camera
  twice). Owns `getUserMedia`, runs MediaPipe FaceLandmarker (WASM) for
  landmarks and opencv.js's `calcOpticalFlowPyrLK` for point tracking, and
  pushes `{metrics, movement}` to the main process every frame (~30fps)
  over `ipcRenderer.send('tracking:frame', ...)`.
- **UI renderers** (config, buttons, overlay) — unchanged in spirit from
  the Electron migration. Their preload contract
  (`window.backend.send(message)` / `window.backend.on(channel, cb)`) is
  preserved byte-for-byte: from a renderer's point of view, "backend" was
  already an abstract message source, not literally a child process, so
  `ipcRelay.ts`'s re-emit pattern and every `backend:*` channel name stay
  as-is. Only what backs `backend.send`/`backend.on` changes, from a
  `BackendProcess` (child_process + stdio framing) to an in-process
  `Engine` (`EventEmitter`).

```
tracking renderer --ipcRenderer.send('tracking:frame')--> ipcMain
  --> Engine.onFrame(metrics, movement) --> gesture eval --> mouseController (nut-js)
  --> Engine emits 'message' (frame/status/action/...) --> ipcRelay --> UI renderers
                                                                          (unchanged)
UI renderer --window.backend.send(cmd)--> ipcMain('backend:send')
  --> Engine.handleCommand(cmd)   [was: child.stdin.write]
```

## Folder layout

`electron/` stops nesting; its contents become the repo root. Final
top-level layout:

```
src/
  modules/    # main-process Node logic
    engine.ts            # was engine.py + backend.py's BackendServer
    gestures.ts           # was gestures.py
    mouseController.ts    # was mouse_controller.py
    config.ts             # was config.py
    clickLog.ts            # was click_log.py
    win32.ts               # koffi shim: COM touch-keyboard toggle, registry, foreground window title
    tray.ts, trayState.ts, ipcRelay.ts   # unchanged from electron/src/main
    windows/               # configWindow.ts, buttonsWindow.ts, overlayWindow.ts, buttonsPosition.ts, trackingWindow.ts (new)
    index.ts                # app bootstrap (was electron/src/main/index.ts)
  ui/         # everything that runs in a renderer (Chromium context)
    tracking/               # hidden window: camera + FaceLandmarker + opencv.js + point tracker
      faceMetrics.ts         # was tracker.py
      pointTracker.ts        # was point_tracker.py
      index.html, index.ts
    config/                  # was electron/src/renderer/config
    buttons/                 # was electron/src/renderer/buttons
    overlay/                 # was electron/src/renderer/overlay
    preload/                 # was electron/src/preload
tests/        # was electron/tests, plus ported gesture/mouse/config/clickLog suites
assets/       # tray icons, icon.ico (generate_icon.py dropped, no Python)
package.json, tsconfig.json, tsconfig.renderer.json, vitest.config.ts,
electron-builder.yml, scripts/   # all move from electron/ to repo root
```

`backendProcess.ts`, `backendCommand.ts`, and `protocol.ts` (the stdio
child-process plumbing and its line-framing) are deleted outright — there
is no longer a child process to spawn or a wire format to frame.

## Component mapping

| Python (deleted) | Node destination | Notes |
|---|---|---|
| `backend.py` (`BackendServer`) | `src/modules/engine.ts` command dispatch | `handle_command`'s per-type dispatch table ports ~1:1; status/frame push loops become `setInterval`-driven instead of daemon threads |
| `modules/engine.py` (`Engine`, `SharedState`) | `src/modules/engine.ts` | `control_enabled`/`paused`/`no_face` state and `_drive_control`'s active/was-active sequencing port directly; the camera-read loop is replaced by the tracking renderer's per-frame push |
| `modules/tracker.py` | `src/ui/tracking/faceMetrics.ts` | landmark indices (33, 263, 168, 152, 61, 291, 105, 334, 159, 386, 1, 10, ...) are unchanged — MediaPipe FaceLandmarker uses the same 468-point topology as the Python `FaceMesh` solution, so this is a mechanical port of the distance/ratio math, not a re-derivation |
| `modules/point_tracker.py` | `src/ui/tracking/pointTracker.ts` | opencv.js `calcOpticalFlowPyrLK` with the same `winSize`/`maxLevel`/`criteria`/`minEigThreshold`; pruning/seeding math (`prune_points`, `should_add_point`, `mean_movement`) ports directly, still pure and unit-testable |
| `modules/gestures.py` | `src/modules/gestures.ts` | pure logic, no OS/camera dependency — the most direct port in the codebase |
| `modules/mouse_controller.py` | `src/modules/mouseController.ts` | nut-js (`mouse.setPosition`, `.getPosition`, `.click`, `.scrollUp/Down`, `.pressButton/releaseButton`) replaces pynput; `accelerate`/`clamp` port unchanged; the per-frame loop becomes `async` since nut-js's position read/write are promise-based |
| `modules/config.py` | `src/modules/config.ts` | JSON load/save/merge/clamp/legacy-gesture-name migration, direct port |
| `modules/click_log.py` | `src/modules/clickLog.ts` | Node rotating-write (roll-your-own or a small rotation helper) replacing Python `logging.handlers.RotatingFileHandler`; foreground-window title via `win32.ts` |
| `modules/preview.py` | dropped as a standalone module | the tracking renderer already holds the frame in a `<canvas>` with the nose-dot/eye-line overlay drawn on it; JPEG is produced there (`canvas.toBlob('image/jpeg', 0.8)`) instead of via `cv2.imencode`, same quality, same wire shape (`frame` message unchanged) |
| `modules/ipc_protocol.py` + `electron/.../protocol.ts` | deleted | replaced by typed `ipcMain`/`ipcRenderer` channels; no line-delimited JSON framing needed once both sides are in-process |
| `virtual_keyboard.py` | `src/modules/win32.ts` | COM `ITipInvocation::Toggle` via koffi (`ole32.dll`), `FindWindowW`/`IsWindowVisible` visibility poll (`user32.dll`), registry floating-layout preference — none of this is expressible through nut-js, which only does synthetic input |
| `voice_typing.py` | `src/modules/mouseController.ts` (or sibling `keyboard.ts`) | nut-js `keyboard.pressKey(Key.LeftSuper, Key.H)` / `releaseKey` |
| `_primary_screen_size()` (`ctypes.windll.user32.GetSystemMetrics`) | Electron's own `screen` module | `screen.getPrimaryDisplay().size` — already imported in `windows/buttonsWindow.ts`/`overlayWindow.ts` today, no new dependency needed for this piece |
| `ui/__init__.py` (empty) | — | already-vestigial legacy, deleted with no replacement |

## Native integration: two libraries, not one

**nut-js** (`@nut-tree-fork/nut-js`) handles everything that is synthetic
input: cursor move/read, click, scroll, button press/release (drag),
Win+H. **koffi** (`src/modules/win32.ts`) handles the handful of things
nut-js structurally cannot do: invoking a COM interface
(`ITipInvocation::Toggle`), reading/writing the registry, and reading the
foreground window's title. Gesture and mouse-math code never touches
either library directly — both are isolated behind `mouseController.ts`
and `win32.ts` respectively.

nut-js's async API is the one real behavior change: `MouseController`'s
per-frame position read (`self._mouse.position`, synchronous today)
becomes `await mouse.getPosition()`. The yield-detection and dwell-click
logic, which both compare the live OS cursor position against a
controller-remembered position every frame, keep their exact comparison
logic — only the calls that fetch/set that position become awaited. At
~30fps this should have headroom to spare; it gets a real perf check once
the tracking loop is running end-to-end, not before.

## Camera pipeline requirements

- `FaceLandmarker`'s model asset (`face_landmarker.task`, a few MB) and
  opencv.js's WASM binary must be vendored into the repo and loaded from
  a local path, not fetched from a CDN at runtime — the current Python
  build already bundles MediaPipe's model data
  (`collect_data_files('mediapipe')` in the now-deleted `backend.spec`),
  and the app must stay equally offline-capable after the port.
- `FaceLandmarker` runs in `VIDEO` mode (`detectForVideo(videoEl,
  timestampMs)`), called once per animation frame against the hidden
  window's `<video>` element — this returns synchronously per call,
  matching the existing per-frame cadence.
- Camera-open failure (`getUserMedia` rejection) is reported from the
  tracking renderer to main via `ipcRenderer.send('tracking:camera-error')`,
  which main handles exactly like today's `error` protocol message
  (`dialog.showErrorBox`, then quit).

## What gets deleted

`.venv/`, `__pycache__/`, `.pytest_cache/`, `build/backend/`,
`dist/facemesh-mouse-backend.exe`, `requirements.txt`,
`requirements-dev.txt`, `pyproject.toml`, `backend.spec`, `run.py`,
`src/facemesh_mouse/` (the whole package), `tests/*.py` +
`tests/__pycache__/`, `assets/generate_icon.py`. `electron-builder.yml`
loses its `extraResources`/backend-exe bundling block entirely — one
Electron app, nothing else to stage. `dist:full`'s PyInstaller step is
gone; `npm run dist` builds the whole app in one pass.

## Testing

The 11 pytest files' coverage moves to vitest, alongside the 7 existing
TS suites, targeting the same pure-logic boundaries:

- `gestures.ts` — hold/cooldown/release-debounce state machine, direct
  port of `test_gestures.py`.
- `mouseController.ts`'s pure `accelerate`/`clamp` functions — direct
  port of `test_mouse_controller.py`'s math tests; the nut-js-driving
  parts stay manually-verified (real display/OS mouse), matching this
  project's existing policy for camera/OS-dependent code paths.
- `config.ts` — load/save/merge/clamp/legacy-name migration, direct port
  of `test_config.py`.
- `clickLog.ts` — direct port of `test_click_log.py`, `win32.ts`'s window-
  title lookup mocked the same way `_foreground_window_title` was
  injectable in Python.
- `pointTracker.ts`'s `prune_points`/`should_add_point`/`mean_movement`
  math — direct port of `test_point_tracker.py`; the opencv.js
  `calcOpticalFlowPyrLK` call itself stays manually-verified, same reason
  the Python version never unit-tested the camera-dependent half.
- `engine.ts`'s command dispatch (`start`/`stop`/`pause`/`resume`/
  `update_config`/`save_config`/`open_keyboard`/`open_voice_typing`) —
  direct port of `test_backend.py`, against a fake `Engine` with no real
  window/camera involved, same shape as today's `handle_command` tests.
- **Removed**: `test_tracker.py`/`test_preview.py`'s pixel-level
  assertions that depended on OpenCV's exact drawing primitives —
  `faceMetrics.ts`'s distance/ratio math is still covered, but the
  overlay-drawing pixels are not.

## Packaging

`electron-builder`, `nsis` target, Windows-only (unchanged). No more
PyInstaller step, no `extraResources` backend exe — `files: - dist/**/*`
now contains the entire app, tracking renderer included. The vendored
`face_landmarker.task` and opencv.js WASM ship as static assets copied by
`scripts/copyStaticAssets.mjs`, the same script that already copies tray
icons.

## Out of scope (YAGNI)

- Cross-platform support (macOS/Linux) — `win32.ts`'s COM/registry calls
  and the app's Windows-only assumptions (taskbar height, `TabTip.exe`)
  are untouched by this port; nut-js being cross-platform-capable doesn't
  change that.
- Any visual redesign — this is a like-for-like engine port, same as the
  Electron migration was a like-for-like UI port.
- Changing the gesture set, config schema fields, default values, or
  `config.json`'s on-disk shape — existing user configs must still load
  unchanged.
- Simplifying the preview pipeline beyond re-sourcing the JPEG (e.g.
  streaming raw video frames instead of JPEG-over-IPC) — out of scope for
  this port, could be a later cleanup once the port is stable.
