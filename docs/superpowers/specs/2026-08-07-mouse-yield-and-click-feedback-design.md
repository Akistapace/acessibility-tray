# FaceMesh Mouse — Yield to Physical Mouse, Click Feedback & Click Log — Design Spec

**Date:** 2026-08-07
**Status:** Approved
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (v1),
`2026-08-05-usability-anchor-mode-design.md` (v2),
`2026-08-06-single-instance-background-startup-design.md` (v3),
`2026-08-07-gesture-expansion-modern-ui-design.md` (v4),
`2026-08-07-optical-flow-tracking-design.md` (v5)

## Purpose

Three related gaps in day-to-day use:

1. **The app fights a physical mouse.** Touching the trackpad/mouse while
   head-tracking is active doesn't hand control over — the next tracked
   frame just overwrites wherever the physical device moved the cursor to.
2. **Clicks are invisible.** A gesture-triggered click gives no on-screen
   confirmation separate from whatever the clicked target does, which
   matters more here than for a physical mouse because the trigger (a
   blink, a brow raise) has no tactile feedback of its own.
3. **There's no record of what the app did.** No way to review after the
   fact what gestures fired, what actions they took, or when.

This spec adds: yielding cursor control to a physical mouse touch and
auto-resuming after it goes quiet, a tray-icon indicator for the yielded
state, a visual pulse at the cursor on every gesture-triggered action, and
a rotating local log of every action fired.

## Approach: Yielding to the Physical Mouse

### Detection

`MouseController` already knows the exact position it last wrote to
`self._mouse.position` (`_cursor_x`/`_cursor_y`, from v5). Each frame,
before applying tracked movement, it compares the OS cursor's actual
current position against that last-written value. A difference beyond a
small tolerance (`YIELD_DETECT_PX = 2`, absorbing OS cursor-position
rounding) means something other than this controller moved the cursor —
the physical mouse. No polling thread, no OS hook: the comparison rides
the existing per-frame `move_cursor` call, so detection latency is one
frame.

### State machine

`MouseController` gains a `yielded: bool` and `_yield_started_at: float |
None`. On detecting an external move:

- Enter yielded: stop applying tracked movement to the cursor (gestures
  still fire — see Out of Scope).
- Set/refresh `_yield_started_at` to now.

While yielded, every frame still checks the OS cursor position:

- If it moved again since the last check, refresh `_yield_started_at`
  (the user is still using the physical device).
- If `now - _yield_started_at >= yield_resume_after_s` (config field,
  default 3.0, GUI slider 1–10s) with no further movement, resume:
  `reanchor()` against the current (physical-mouse) position — which is
  already the correct behavior, since reanchor syncs to wherever the OS
  cursor actually is — and clear `yielded`.

This reuses `reanchor`'s existing contract from v2/v5 instead of adding a
second resume path.

### Engine wiring

`Engine._drive_control` calls `move_cursor` every active frame regardless
of yield state — the yield/resume decision lives inside `MouseController`,
not the engine, so `_drive_control` doesn't need to know about it. Gesture
evaluation and `fire_action` continue to run while yielded (see Out of
Scope for why).

## Approach: Tray Indicator

`tray.py` gains a fourth icon color/state. Precedence, highest first:
**paused** (existing) → **yielded to mouse** (new) → **no face** (existing)
→ **running** (existing). `main.py`'s existing 500ms poll loop
(`_poll_no_face`) reads `engine.mouse_controller.yielded` alongside the
existing `no_face` check and calls a new `tray.set_yielded(bool)`, mirroring
`set_no_face`'s existing pattern. Tooltip text explains the state in
Portuguese ("Controle pelo mouse físico").

## Approach: Click Feedback (the "pulse")

### Why a pulse, and why click-through

A borderless, topmost `tk.Toplevel` draws an expanding-and-fading ring
centered on the cursor position at the moment of the action, then destroys
itself after ~300ms. It must be click-through
(`WS_EX_TRANSPARENT`/`WS_EX_LAYERED` via `ctypes`, applied to the
Toplevel's HWND) — otherwise the overlay window itself would intercept the
very next click, which would be actively harmful for a tool whose whole
purpose is clicking.

### Trigger path

`MouseController.fire_action` (v1) already knows the gesture name, the
resolved action, and can read the cursor position. It gains a call to an
injected `on_action: Callable[[str, str, tuple[int, int]], None] | None`
callback (default `None`, so `MouseController` stays independently
testable with no GUI dependency) right before executing the pynput action.
`main.py` wires this callback to a small `click_feedback.py` module's
`show_pulse(x, y)` and to the click logger (below) in one function, since
`fire_action` runs on the engine thread and both the overlay and the
logger need to be invoked safely — the overlay via `root.after(0, ...)`
(the established pattern from every other cross-thread Tk call in this
codebase), the logger directly (the stdlib logging module is thread-safe).

### Scope of the pulse

Fires for every gesture action except `none`. Does not fire for cursor
movement itself — only discrete actions (clicks, scrolls).

## Approach: Click Log

### What's recorded

One line per fired action: timestamp, gesture name, resolved action,
cursor position, and the foreground window's title at that moment. Window
title is read via `ctypes` (`GetForegroundWindow` + `GetWindowTextW`) —
already how `single_instance.py`'s neighbors in this codebase reach the
Win32 API, no new dependency.

```
2026-08-07 14:32:07,123 blink_a left_click (842, 511) "Novo separador - Google Chrome"
```

### Storage

Python's stdlib `logging.handlers.RotatingFileHandler`: `clicks.log` in the
app directory, `maxBytes=1_000_000`, `backupCount=3` — roughly the last
few thousand actions, self-limiting, never sent anywhere. Added to
`.gitignore` alongside the existing `config.json` exclusion. A toggle in
the GUI (`CalibrationConfig`-adjacent boolean, default on) lets the user
turn logging off entirely; when off, `click_log.py`'s logger is never
attached, not merely filtered, so disabling it costs nothing per click.

## Data Flow Summary

```
gesture fires → GestureEngine.evaluate → MouseController.fire_action
                                              │
                                              ├─ executes pynput action (unchanged)
                                              └─ on_action(gesture, action, (x, y))
                                                     │
                                          main.py's wiring, off the engine thread
                                                     │
                                    ┌────────────────┴────────────────┐
                                    │                                 │
                          root.after(0, show_pulse)          click_log.record(...)
                          (click_feedback.py, Tk-thread)      (stdlib logging, thread-safe)
```

## Error Handling

- If `GetForegroundWindow`/`GetWindowTextW` fail or return nothing (rare,
  e.g. mid-transition between windows), the log line records the window
  title as `"?"` rather than skipping the line — the action itself still
  happened and is still worth a record.
- If the click-feedback Toplevel fails to create (unlikely; no known
  failure mode on Windows), the exception is caught and logged to stderr
  once rather than raised on the Tk thread, since a missing visual pulse
  must never be allowed to crash background tracking.

## Testing

- **Yield state machine** (`MouseController`, `FakeMouse` + a fake clock,
  extending the existing test double pattern from v2/v5): detecting an
  external move enters yielded and stops applying tracked movement;
  continued external movement keeps refreshing the resume timer; resuming
  after the configured quiet period reanchors to the physical-mouse
  position with no jump; movement below `YIELD_DETECT_PX` is not
  misdetected as external.
- **Click log** (`tmp_path`, stdlib `logging` — no mocking needed): one
  call to `record()` produces one parseable line with all five fields;
  rotation triggers past `maxBytes`; the disabled-logger path attaches no
  handler.
- **Overlay**: a smoke test under the existing module-scoped Tk root
  fixture (`tests/test_panels.py`'s `root`/`container` pattern from v4) —
  construct and immediately destroy the pulse Toplevel, assert it doesn't
  raise and that click-through styling is applied via
  `GetWindowLongW`/`WS_EX_TRANSPARENT` bit check.
- **Tray indicator precedence**: manual checklist, consistent with the
  rest of `tray.py` (real system tray, not testable in pytest).
- **Manual checklist additions**: touch the trackpad while tracking is
  active — cursor stops following the head; keep moving it — control stays
  yielded; stop touching it — control resumes after the configured delay
  with no jump. Trigger a mapped gesture — see the pulse at the cursor.
  Check `clicks.log` after a session — one line per action, readable.
  Toggle logging off — confirm no new lines appear.

## Out of Scope (YAGNI)

- Blocking gesture evaluation while yielded. Gestures keep firing during a
  yield (e.g. a mapped blink can still click at the physical mouse's
  current position) — the yield only concerns cursor *movement*. Fully
  suppressing gestures during yield is a bigger behavioral question (would
  a user expect "hands-free is fully off" or "just don't move the cursor"?)
  and isn't what was asked for.
- A configurable pulse color, size, or duration — one visual style ships;
  revisit if it proves wrong in use.
- Structured/queryable log format (SQLite, JSON lines) — plain text lines
  are sufficient for "review what happened," and match this project's
  existing preference for the simplest storage that works (`config.json`
  is plain JSON, no database anywhere in the app).
- Reading the actual clicked UI element (link text, button name) via UI
  Automation — considered and explicitly declined: real per-click latency
  cost, a new dependency, and inconsistent support across browsers and
  especially Electron/Java apps. The foreground window title is the
  ceiling for this pass.
- Log viewing inside the app's own GUI — the log is a plain text file the
  user can already open; an in-app viewer is a separate feature.
