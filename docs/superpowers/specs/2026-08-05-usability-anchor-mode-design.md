# FaceMesh Mouse — Usability, Anchor Mode & Deadzone — Design Spec

**Date:** 2026-08-05
**Status:** Approved
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (original v1 spec)

## Purpose

V1 shipped with an absolute-position cursor mapping, a Portuguese-labeled but
still fairly technical config GUI, and no way to reposition the head without
the cursor jumping. This spec covers five related usability improvements
requested after using v1:

1. **Anchor-relative cursor mapping** — replaces absolute position mapping
   so the existing pause/resume action (hotkey `Ctrl+Alt+P`, tray menu) now
   behaves like lifting a physical mouse off the desk, repositioning your
   hand, and putting it back down: pause freezes the cursor, resume
   continues from the same cursor position using the new head position as
   the reference point, with zero jump.
2. **Play/pause calibration capture** — the four calibration buttons become
   record toggles that track the most extreme value reached during
   recording, instead of requiring a precisely-timed single click, plus a
   live on-screen guide during recording.
3. **Deadzone** — a small ignored-movement threshold (in screen pixels) so
   micro head tremor doesn't jitter the cursor when the user is trying to
   hold still.
4. **Sensitivity slider** — a user-adjustable multiplier on top of the
   calibration-derived scale, so cursor speed can be tuned without
   recalibrating.
5. **Full GUI usability pass** — numbered step layout, plain-language
   labels, progress-bar metric displays instead of raw decimals, and
   contextual help text, aimed at a non-technical end user.

## Approach: Anchor-Relative Mapping

### Why relative instead of absolute

Absolute mapping (v1) ties cursor position directly to where the nose is
within the calibrated range. This has two problems for a hands-free tool:
the user must keep their head within a narrow calibrated zone for the whole
session, and there's no way to "reset" a comfortable neutral head position
without recalibrating from scratch. Switching to **anchor-relative** mapping
mirrors how a physical mouse works: position is an accumulation of
movement deltas, and lifting/replacing the mouse (pause/resume) resets the
reference point without moving the cursor.

### Mechanism

`MouseController` tracks:
- `_prev_nose_x/y` — nose position as of the last frame it moved the cursor.
- `_target_x/y` — the accumulating (unsmoothed) cursor position.
- `_smoothed_x/y` — EMA-smoothed cursor position actually applied to the OS
  cursor (unchanged mechanism from v1, same `smoothing` config field).

Each active frame:
```
dx = nose_x - prev_nose_x
dy = nose_y - prev_nose_y
prev_nose_x, prev_nose_y = nose_x, nose_y

if abs(dx) * scale_x < deadzone_px: dx = 0
if abs(dy) * scale_y < deadzone_px: dy = 0

target_x = clamp(target_x + dx * scale_x, 0, screen_w - 1)
target_y = clamp(target_y + dy * scale_y, 0, screen_h - 1)

smoothed_x = ema_smooth(smoothed_x, target_x, smoothing)
smoothed_y = ema_smooth(smoothed_y, target_y, smoothing)
mouse.position = (smoothed_x, smoothed_y)
```

`scale_x = (screen_w / (x_max - x_min)) * sensitivity`, `scale_y = (screen_h
/ (y_max - y_min)) * sensitivity`, using the same calibrated extremes as v1
— calibration still determines "how much head movement crosses the
screen," it just drives a per-frame scale factor instead of an absolute
bound. `sensitivity` is the new user-facing multiplier (see Sensitivity
Slider below), default `1.0` so a fresh config behaves exactly like the
calibration-only scale.

### Reanchoring

A new `MouseController.reanchor(metrics)` resets all tracked state:
```
prev_nose_x, prev_nose_y = metrics.nose_x, metrics.nose_y
cur_x, cur_y = mouse.position   # actual current OS cursor position
target_x, target_y = cur_x, cur_y
smoothed_x, smoothed_y = cur_x, cur_y
```
Reading the real OS cursor position (rather than the last computed value)
means if the user nudged a physical mouse while paused, tracking resumes
from wherever the cursor actually is.

`Engine._run` calls `reanchor()` whenever the immediately preceding frame
did **not** drive the cursor. One `was_active` bool covers every case that
needs a fresh anchor without separate flags per cause:
```
was_active = False
loop:
    ...
    if metrics is None:
        was_active = False
        continue
    active_now = control_enabled.is_set() and not paused.is_set()
    if active_now:
        if not was_active:
            mouse_controller.reanchor(metrics)
        mouse_controller.move_cursor(metrics)
        fire gestures...
    was_active = active_now
```
This naturally reanchors on: first start, resume-from-pause, and
face-reacquired-after-loss (avoids a teleport when the face drops out of
frame and returns).

No new hotkey or gesture is introduced — the existing pause/resume
(`Ctrl+Alt+P`, tray menu "Pausar/Retomar") is the trigger. The GUI's help
text (see Section 4) explains this dual purpose explicitly.

## Play/Pause Calibration Capture

The four calibration buttons ("Capturar Cima/Baixo/Esquerda/Direita")
become toggles:

- **▶ Gravar [direção]** starts recording: disables the other three capture
  buttons (only one direction records at a time), seeds the running extreme
  from the current live nose value, and shows a guide line + live extreme
  readout (e.g. "Mova a cabeça o máximo para cima e clique em Parar quando
  terminar." / "Extremo atual: 0.241").
- While recording, the existing 33ms preview tick (`ConfigWindow._tick`)
  additionally compares the live metric against the running extreme each
  frame and updates it if more extreme (min for up/left, max for
  down/right).
- **⏸ Parar** locks the recorded extreme into `config.calibration`,
  re-enables the other three buttons, and reverts the label to ▶.

This removes the precision-timing requirement of v1's instant-capture
buttons — the user can drift past the true extreme and back without
losing it.

## Deadzone

New `CalibrationConfig.deadzone_px: float` field (default `4.0`), exposed as
a slider (0–15px) in the GUI's calibration step, labeled in pixel terms
("Ignorar tremores de até N px") rather than raw normalized units, since
pixels are the intuitive unit for an end user. Applied per-axis per-frame as
described above — small camera/head noise below the threshold contributes
zero movement; real movement passes through unaffected.

## Sensitivity Slider

New `CalibrationConfig.sensitivity: float` field (default `1.0`, slider
range `0.3`–`3.0` in the GUI), labeled "Sensibilidade" in the calibration
step next to the deadzone slider. Multiplies `scale_x`/`scale_y` directly
(see Mechanism above) — below 1.0 the user must move their head further to
cross the screen (finer control), above 1.0 less head movement covers more
screen (faster, twitchier). This is a runtime multiplier only; it doesn't
change the stored calibration extremes, so recalibrating and adjusting
sensitivity stay independent actions. An exposed smoothing (EMA) slider was
considered and explicitly declined as out-of-scope for this pass.

## GUI Usability Pass

Scope: full visual pass, not just relabeling.

- **Numbered step layout**: "1. Calibrar movimento" → "2. Mapear gestos" →
  "3. Iniciar", replacing the current single flat form. Step 1 holds both
  the deadzone slider and the sensitivity slider alongside the capture
  buttons.
- **Progress-bar metrics**: `ear_a`, `ear_b`, `mouth_open_ratio`,
  `eyebrow_raise_ratio` render as `ttk.Progressbar` fills relative to that
  gesture's configured threshold (value / threshold, capped at 100%),
  instead of raw 3-decimal numbers — gives a "how close to triggering"
  visual instead of an unlabeled float.
- **Contextual help text** under each step (short, one/two lines): what to
  do and why, in plain Portuguese.
- **Pause/resume ("lift the mouse") callout**: explicit help text
  explaining `Ctrl+Alt+P` freezes the cursor, lets the user reposition
  their head to a comfortable neutral point, and resuming continues from
  the same cursor position with no jump — this is the practical surface of
  the anchor-relative mapping change, and needs to be visible so the user
  actually discovers it.
- **Play/pause capture buttons** get ▶/⏸ characters, not new image assets.
- **Start button** relabeled to something clearer than "Iniciar tracking"
  (e.g. "▶ Iniciar controle do mouse").
- Gesture rows ("Piscar olho A/B" etc.) keep their current labels — the
  A/B ambiguity is intentional (camera mirroring makes "left/right"
  unreliable) and already has explanatory text above the rows; only the
  surrounding layout/spacing changes.

## Testing

- `tests/test_mouse_controller.py` currently tests `map_normalized_to_screen`
  (absolute mapping), which is removed. Replace with tests for the new pure
  delta-scaling function (raw delta + scale + deadzone → applied delta,
  no OS/display dependency), including cases where `sensitivity` != 1.0
  scales the applied delta proportionally, and for `MouseController.reanchor`
  resetting `_prev_nose_x/y`, `_target_x/y`, and `_smoothed_x/y` to the OS
  cursor position.
- `ema_smooth` is unchanged — no new tests needed beyond existing coverage.
- `Engine`'s `was_active` reanchor-trigger logic gets a focused test:
  synthetic sequence of (metrics, paused-state) frames asserting
  `reanchor()` is called exactly on start, resume-from-pause, and
  face-reacquired transitions, not on every active frame.
- Manual checklist addition: verify no visible cursor jump when pausing,
  moving the head to a new neutral position, and resuming.

## Out of Scope (YAGNI)

- Exposing the EMA `smoothing` value as a GUI control (declined — stays a
  config-file-only field, default unchanged).
- A dedicated "recenter without full pause" action — pause/resume already
  covers the anchor-reset need.
- Multi-monitor-aware calibration (still out of scope per v1).
