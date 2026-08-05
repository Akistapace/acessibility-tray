# FaceMesh Mouse Control — Design Spec

**Date:** 2026-08-05
**Status:** Approved

## Purpose

Hands-free mouse control using webcam face tracking. Nose-tip position drives
cursor movement; facial gestures (blinks, mouth open, eyebrow raise) trigger
configurable mouse actions (left/right click, double click, scroll). A GUI
lets the user calibrate movement range and map gestures to actions. Once
configured, tracking continues in the background (no visible window), with a
system tray icon and global hotkeys for pause/resume and reopening config.

The system must also be packageable as a standalone Windows `.exe` via
PyInstaller so it can run without a Python install on the target machine.

## Background / Constraint Note

The original idea was tongue-tip tracking for cursor movement. MediaPipe
FaceMesh does not expose tongue landmarks (only face contour, eyes/iris, and
lip landmarks), and reliable tongue detection would require a color/shape
heuristic (fragile, lighting-dependent) or a custom-trained model (heavy
lift). Decision: **use nose-tip position as the cursor-control proxy**
instead of literal tongue tracking — same "point your face to move the
cursor" interaction, backed by a landmark that FaceMesh tracks natively and
robustly.

## Stack

- **Python 3.11** — target version for MediaPipe compatibility. Machine
  currently has no real Python install (only the Microsoft Store execution
  alias stub) — must be installed first.
- **opencv-python** — webcam capture, frame handling.
- **mediapipe** — `FaceMesh` solution, `refine_landmarks=True` for iris
  landmarks (needed for eye-blink detection).
- **pynput** — mouse control (move/click/scroll) and global hotkey listener.
  Chosen over `pyautogui` for lower per-call overhead during continuous
  cursor movement and because its hotkey listener is thread-friendly.
- **tkinter** (stdlib) — configuration GUI window, webcam preview canvas,
  calibration wizard, gesture-mapping form.
- **pystray** — system tray icon + menu for background mode.
- **PyInstaller** — packaging into a standalone `.exe`.
- **pytest** — unit tests for pure logic.

## Components

| Module | Responsibility |
|---|---|
| `tracker.py` | Runs MediaPipe FaceMesh on a frame; extracts normalized nose-tip position, left/right eye-aspect-ratio (EAR), mouth-open ratio, eyebrow-raise ratio. Pure function of a frame → metrics dataclass. Returns `None` metrics (face-not-found) when no face is detected. |
| `gestures.py` | State machine converting raw per-frame metrics into discrete, edge-triggered gesture events: `blink_left`, `blink_right`, `blink_both`, `mouth_open`, `eyebrow_raised`. Each event has a configurable threshold and a cooldown to prevent repeat-firing while held. |
| `mouse_controller.py` | Applies calibration (4-point range) to normalized nose position, smooths it (EMA), moves the OS cursor via `pynput.mouse.Controller`. Executes mapped actions (left click, right click, double click, scroll up/down) with per-gesture cooldown. Freezes cursor (no movement) when face is not detected. |
| `config.py` | Loads/saves `config.json`: gesture→action mapping, per-gesture thresholds, calibration bounds (min/max normalized nose x/y), smoothing factor. |
| `config_gui.py` | Tkinter window: live webcam preview with landmark overlay, 4-point calibration wizard (user moves head to each extreme, clicks "capture"), a 4-row form (one per gesture) with an action dropdown (None / Left click / Right click / Double click / Scroll up / Scroll down) and a live threshold indicator bar per gesture. "Start tracking" button hides the window and hands off to background mode. |
| `tray.py` | `pystray.Icon` with menu: Pause/Resume, Open Config, Quit. |
| `hotkeys.py` | `pynput.keyboard.GlobalHotKeys` — one hotkey toggles pause/resume, one reopens the config window. |
| `main.py` | Entry point. Loads or creates config, shows `config_gui` first, then on "Start tracking" launches the background tracking thread, tray thread, and hotkey thread, keeping the Tk root alive (hidden) as the event-loop anchor. |

## Data Flow / Threading Model

- The Tk `root` window is created once and lives for the whole process
  lifetime — closing the config view calls `root.withdraw()`, reopening
  calls `root.deiconify()`. It is never destroyed, so there's only ever one
  Tk mainloop.
- Camera capture + FaceMesh inference + gesture detection + mouse control
  run in one daemon background thread, gated by a `threading.Event` (paused
  / running).
- The tray icon runs in its own thread (`pystray.Icon.run()` is blocking).
- The global hotkey listener runs in its own thread.
- Tk is not thread-safe: any interaction with `root` from the tray or
  hotkey threads (e.g. "Open Config" clicked) is marshalled via
  `root.after(0, callback)`.
- When FaceMesh reports no face in frame, the background loop skips cursor
  movement and gesture evaluation for that frame (cursor holds position);
  the tray icon's tooltip reflects "No face detected".

## Calibration & Cursor Mapping

User is prompted (in `config_gui`) to hold their head at each of 4 extremes
(up, down, left, right) and press "capture" to record the normalized
nose-tip bounds. At runtime, the current nose position is linearly mapped
from that captured range to full screen coordinates (via
`pynput`/`tkinter` screen size query), then passed through an exponential
moving average (configurable smoothing factor, default tuned for a balance
of responsiveness vs. jitter reduction) before being applied to the cursor.

## Gesture Mapping (config.json shape)

```json
{
  "calibration": {
    "x_min": 0.0, "x_max": 0.0,
    "y_min": 0.0, "y_max": 0.0,
    "smoothing": 0.3
  },
  "gestures": {
    "blink_left":     { "action": "left_click",  "threshold": 0.21, "cooldown_ms": 400 },
    "blink_right":     { "action": "right_click", "threshold": 0.21, "cooldown_ms": 400 },
    "blink_both":      { "action": "none",        "threshold": 0.21, "cooldown_ms": 400 },
    "mouth_open":      { "action": "double_click","threshold": 0.35, "cooldown_ms": 600 },
    "eyebrow_raised":  { "action": "scroll_up",   "threshold": 0.15, "cooldown_ms": 300 }
  }
}
```

`action` values: `none`, `left_click`, `right_click`, `double_click`,
`scroll_up`, `scroll_down`.

## Error Handling

- Camera not found / access denied at startup → error dialog in the config
  GUI before any background thread starts; user cannot proceed to "Start
  tracking" without a working camera preview.
- No face detected during background tracking → cursor freezes, no
  gesture evaluation; not treated as an error, just a transient state shown
  in the tray tooltip.
- Each gesture has an independent cooldown so a held expression (e.g. an
  extended blink) fires the action once, not repeatedly per frame.

## Testing

- **Unit tests (pytest)**, no camera/OS interaction required:
  - `gestures.py` state machine given synthetic metric sequences (mocked
    EAR/mouth/eyebrow values) → correct edge-triggered events + cooldown
    behavior.
  - Calibration mapping function: normalized nose position + captured
    bounds → expected screen coordinates.
  - EMA smoothing math: sequence in → expected smoothed sequence out.
  - `config.py` load/save round-trip, including defaults when file is
    missing/partial.
- **Manual checklist** (camera, mouse, tray, hotkeys, exe build) — not
  automatable in this environment; covered by a manual test pass during
  implementation and before calling the feature done.

## Packaging as .exe

`PyInstaller --onefile`, with explicit data collection flags since
MediaPipe and OpenCV ship non-Python binary assets that PyInstaller's
default analysis misses:

```
pyinstaller --onefile --windowed ^
  --collect-data mediapipe --collect-all cv2 ^
  --add-data "assets;assets" ^
  main.py
```

Known caveats to document in the README:
- Resulting exe is large (roughly 200–400MB) due to bundled MediaPipe/OpenCV/NumPy.
- First launch is slower (unpacking to a temp dir for `--onefile` mode).
- Unsigned exe → Windows SmartScreen will warn on first run.
- Windows camera privacy permission must be granted the first time the
  exe (or the dev build) requests the webcam.

## Out of Scope (YAGNI)

- Multi-monitor-aware calibration (single active display only for v1).
- Literal tongue detection (see Background/Constraint Note).
- Cross-platform packaging (macOS/Linux) — Windows exe only, per request.
- Head-pose (pitch/yaw/roll) based cursor control — nose-tip position only.
