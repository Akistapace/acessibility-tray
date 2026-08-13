# FaceMesh Mouse — Virtual Keyboard Launcher — Design Spec

**Date:** 2026-08-13
**Status:** Approved
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (v1),
`2026-08-05-usability-anchor-mode-design.md` (v2),
`2026-08-06-single-instance-background-startup-design.md` (v3),
`2026-08-07-gesture-expansion-modern-ui-design.md` (v4),
`2026-08-07-optical-flow-tracking-design.md` (v5),
`2026-08-07-mouse-yield-and-click-feedback-design.md` (v6)

## Purpose

The app has no text-input path at all. It moves and clicks the cursor, but a
user who can't reliably use a physical keyboard — the same population the
whole app is built for — still has no way to type. Windows already ships an
accessible on-screen keyboard (`osk.exe`); this app doesn't need to build one,
it needs to make the existing one reachable through the same head-tracked
cursor the rest of the app uses.

## Approach

### `virtual_keyboard.py` (new)

One function: `open_virtual_keyboard() -> None`. Calls
`subprocess.Popen(["osk.exe"])` and swallows any exception (print to stderr),
matching `click_feedback.show_pulse`'s existing rule that a failure in a
secondary feature must never propagate. No `shell=True`. No process tracking
— launching `osk.exe` while it's already running is left to Windows' own
behavior (it's single-instance on its own), not handled here.

### Entry points

Both call `virtual_keyboard.open_virtual_keyboard()` directly; neither tracks
open/closed state:

- **`tray.py`**: a third `pystray.MenuItem`, "Abrir Teclado", between
  "Reabrir Config" and "Sair". `TrayIcon.__init__` gains an
  `on_open_keyboard: Callable[[], None]` parameter, mirroring the existing
  `on_open_config` pattern.
- **`main.py`**: wires `on_open_keyboard=virtual_keyboard.open_virtual_keyboard`
  where `TrayIcon` is constructed.
- **`config_gui.py`**: a `CTkButton` "Abrir Teclado" on the existing "Ajuda"
  tab, above the help text, `command=virtual_keyboard.open_virtual_keyboard`.
  This is the primary target for imprecise cursor control — a full-width
  button is far easier to land a head-tracked click on than the tray icon.

Closing the keyboard is via `osk.exe`'s own window controls, clickable
through the app's existing cursor — no close/toggle path is built.

## Error Handling

If `osk.exe` isn't found or fails to launch (e.g. missing on a non-standard
Windows install), the exception is caught inside
`open_virtual_keyboard`, printed once, and never reaches the caller — a
missing keyboard must not crash tracking, the tray, or the config window,
consistent with how `click_feedback` treats a failed pulse.

## Testing

- `test_virtual_keyboard.py`: `monkeypatch` on `subprocess.Popen` asserts
  `open_virtual_keyboard()` calls it with `["osk.exe"]`; a second test forces
  `Popen` to raise and asserts nothing propagates.
- `tray.py` and `config_gui.py` wiring gets no new automated test, consistent
  with the existing state of both files — there is no `test_tray.py` (pystray
  drives a real system tray icon, not testable under pytest) and
  `config_gui.py`'s shell (as opposed to the panels it hosts) has no test
  file today either.
- **Manual checklist**: click "Abrir Teclado" in the tray menu — OSK opens.
  Click "Abrir Teclado" in the Config → Ajuda tab — OSK opens. Use the
  head-tracked cursor to click a key on the OSK and to click its own close
  button.

## Out of Scope (YAGNI)

- A custom-built on-screen keyboard inside the app. Windows' OSK is already
  accessible, already maintained, and already works with any focused app —
  building one from scratch was considered and explicitly declined.
- Toggle/close-from-tray behavior and any process-state tracking for
  `osk.exe`. The OSK's own window is already reachable and closable through
  the app's cursor; tracking its PID would add state for no behavior gain.
- A tray icon or state indicator reflecting whether the OSK is currently
  open. Nothing else in this feature depends on that state.
- Elevation/UAC handling — `osk.exe` launches under a standard user session
  without a prompt; if that ever proves false on some target machine, it's a
  separate bug, not a design gap.
- Any change to `engine.py`, `mouse_controller.py`, `gestures.py`,
  `hotkeys.py`, `single_instance.py`, or `point_tracker.py`.
