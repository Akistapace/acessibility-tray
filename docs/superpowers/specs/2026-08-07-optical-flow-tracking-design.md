# FaceMesh Mouse — Optical-Flow Tracking (tracky-mouse port) — Design Spec

**Date:** 2026-08-07
**Status:** Approved
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (v1),
`2026-08-05-usability-anchor-mode-design.md` (v2),
`2026-08-06-single-instance-background-startup-design.md` (v3),
`2026-08-07-gesture-expansion-modern-ui-design.md` (v4)

## Purpose

Cursor movement is driven by a single FaceMesh landmark (the nose tip),
scaled linearly from a four-point calibration and smoothed with an EMA. In
use it feels jittery and laggy: the landmark's own frame-to-frame noise goes
straight to the cursor, and the EMA that hides the jitter also adds
latency.

[tracky-mouse](https://github.com/1j01/tracky-mouse) (MIT) solves the same
problem noticeably better. This spec ports its tracking pipeline: many
points tracked by optical flow and averaged, a power-curve acceleration
instead of an EMA, and per-axis sensitivity.

## Why Their Approach Is Steadier

Three mechanisms, each addressing a different failure of ours:

1. **Averaging many points instead of trusting one.** They seed points on
   the face and track them with Lucas-Kanade optical flow, then take the
   arithmetic mean of every surviving point's frame-to-frame delta. A single
   landmark's inference noise is uncorrelated across points, so averaging
   N points cuts it roughly by √N. This is where the *consistency* comes
   from.
2. **A power-curve acceleration instead of a smoothing filter.** Their
   `delta * |delta * 5| ** acceleration` shrinks small movements hard (so
   holding still is genuinely still, and fine positioning is possible) while
   leaving large movements fast. Unlike an EMA it introduces **no latency** —
   each frame's output depends only on that frame's input. This is where the
   *fluidity* comes from.
3. **Optical flow is temporally coherent.** Landmarks are re-inferred from
   scratch each frame; optical flow follows actual image texture from the
   previous frame, so its deltas don't carry per-frame re-detection jumps.

## Pipeline

### Point tracking (`point_tracker.py`, new)

Ported from tracky-mouse's point-tracker class, using OpenCV in place of
jsfeat.

**Seeding.** Each frame with a detected face, offer three landmark
positions as candidate points: nostrils (`98`, `327`) and the midpoint
between the eyes (`168` — already used as our midline anchor). A candidate
is **rejected if it is within `MIN_DISTANCE_TO_ADD = 7.5` px of an existing
point on either axis**. Preferring already-tracked points over fresh ones
is deliberate: an established point already carries motion history, and
adding a near-duplicate would displace it during pruning.

**Tracking.** `cv2.calcOpticalFlowPyrLK` on the grayscale frame, with
tracky-mouse's parameters: `winSize=(20, 20)`, `maxLevel=3`, and
`criteria=(EPS | COUNT, 30, 0.01)`.

**Pruning**, in this order every frame:

- Drop points optical flow reports as lost (`status != 1`).
- **De-duplicate on a spatial grid** of `PRUNING_GRID = 5` px: points are
  bucketed by `(int(x / 5), int(y / 5))` and one survivor is kept per
  bucket. Collapsed points contribute nothing, and clusters would weight
  one part of the face more heavily than the rest.
- **Cull points that have drifted off the face**: drop any point farther
  from the nose tip than the head size, measured on an ellipse stretched
  1.4× horizontally (`hypot((nose_x - x) * 1.4, nose_y - y) > head_size`,
  where `head_size` is the outer-eye-corner distance — landmarks `33` and
  `263`).

**Movement.** `get_movement()` returns the arithmetic mean of
`current - previous` across surviving points, in camera pixels, or
`(0.0, 0.0)` when no points survive.

### Cursor mapping (`mouse_controller.py`)

Per active frame:

```
movement_x, movement_y = point_tracker.get_movement()   # camera pixels

delta_x = accelerate(movement_x * sensitivity_x, acceleration)
delta_y = accelerate(movement_y * sensitivity_y, acceleration)

if abs(delta_x * screen_w) < motion_threshold_px: delta_x = 0.0
if abs(delta_y * screen_h) < motion_threshold_px: delta_y = 0.0

cursor_x -= delta_x * screen_w     # minus: the preview frame is mirrored
cursor_y += delta_y * screen_h
clamp to screen bounds
```

where

```python
def accelerate(delta: float, acceleration: float) -> float:
    return delta * (abs(delta * 5.0) ** acceleration)
```

The motion threshold is applied **after** acceleration, following
tracky-mouse (which follows eViacam): that way the setting's unit is
honestly "screen pixels of cursor movement", not "pixels before a curve is
applied to them".

The EMA (`ema_smooth`) is removed from the cursor path. Acceleration
provides the stability it was there for, without its latency.

### Reanchoring

`reanchor(...)` is kept and still runs on the transitions v2 established
(startup, resume-from-pause, face reacquired), but its job shrinks: it
resyncs the internal cursor position to the real OS cursor (so a physical
mouse nudge while paused isn't fought) and drops all tracked points so the
next frame reseeds. With pure delta accumulation there is no absolute
mapping left to jump.

## Config Schema

`CalibrationConfig` is replaced field-for-field:

| Removed | Added | Default |
|---|---|---|
| `x_min`, `x_max`, `y_min`, `y_max` | `sensitivity_x` | `0.025` |
| `sensitivity` | `sensitivity_y` | `0.05` |
| `smoothing` | `acceleration` | `0.5` |
| `deadzone_px` | `motion_threshold_px` | `0.0` |

Defaults are tracky-mouse's shipped values (its sliders store
`slider / 1000` for sensitivity and `slider / 100` for acceleration;
defaults 25, 50, and 50 respectively). Vertical sensitivity is twice
horizontal because heads travel less vertically than horizontally.

Removed keys in an existing `config.json` are ignored, and the new keys get
their defaults — the old four-point bounds have no meaningful translation
into a sensitivity, so no migration is attempted. Gesture settings, which
live under a separate key, are untouched and keep migrating as in v4.

## GUI

The **Movimento** tab loses the four capture toggles and their recording
state entirely, and becomes four sliders:

| Label | Field | Range |
|---|---|---|
| Sensibilidade horizontal | `sensitivity_x` | 0.005–0.10 |
| Sensibilidade vertical | `sensitivity_y` | 0.005–0.10 |
| Aceleração | `acceleration` | 0.0–1.0 |
| Limiar de movimento | `motion_threshold_px` | 0–10 px |

Each slider gets a one-line description in the same plain-Portuguese
register as the rest of the UI, explaining what it does in terms of felt
behavior ("aceleração alta deixa o cursor lento em movimentos pequenos e
rápido em movimentos grandes").

Dropping the capture buttons also fixes a defect found by running the real
app: the window opened clipped because the capture-button grid and the
sliders stretched the tab content to roughly 1400 px, wider than the
1536×864 screen could show at the window's default position. With the
button grid gone and slider rows given a bounded width, the content fits.
The window additionally sets an explicit initial geometry and a `minsize`.

`CalibrationPanel` keeps its name and its `(parent, config)` /
`.frame` / `.update(metrics)` shape so the shell's wiring is unchanged;
`update` becomes a no-op since nothing on the tab is live anymore.
`cancel_capture()` is removed along with the capture state, and the shell
stops calling it.

## Attribution

The pipeline, its constants (`5` px pruning grid, `7.5` px minimum
add-distance, `20` px window, the `|delta * 5| ** acceleration` curve, the
1.4× ellipse), and the defaults are ported from tracky-mouse, MIT
licensed, © Isaiah Odhner. `point_tracker.py` and the acceleration function
carry a module-level comment naming the project, the license, and the URL.

## Testing

- **`accelerate`** — pure: zero in gives zero out; sign is preserved;
  `acceleration=0` reduces to a linear pass-through (`|d*5|**0 == 1`);
  a higher acceleration shrinks a small delta more than a large one
  (the property the whole curve exists for).
- **Pruning** — pure given synthetic point arrays: lost points dropped;
  two points in the same 5 px bucket collapse to one; a point beyond the
  head-size ellipse is culled while one inside is kept; the 1.4×
  horizontal stretch is asserted by a point that survives vertically but
  not at the same horizontal distance.
- **Seeding** — a candidate within 7.5 px of an existing point on either
  axis is rejected; one farther out on both axes is accepted.
- **`get_movement`** — mean of several points' deltas; `(0.0, 0.0)` with no
  points.
- **Optical flow integration** — a real `cv2.calcOpticalFlowPyrLK` run on a
  synthetic textured image translated by a known offset, asserting the
  recovered movement matches within a pixel. This needs no camera and
  pins the OpenCV call's argument order and return shape, which is the
  part most likely to be wrong.
- **`MouseController`** — with the existing `FakeMouse` double: a movement
  produces the expected screen delta; the motion threshold zeroes a small
  one; `reanchor` resyncs to the OS cursor position.
- **Config** — new fields round-trip; a legacy file with the removed keys
  loads with the new defaults and its gesture mappings intact.
- **GUI** — the four sliders write their fields, via the existing
  module-scoped-root panel tests.
- **Manual** — cursor visibly steadier while holding still than the v4
  build; fine positioning onto a small target possible; large movements
  still cross the screen quickly.

## Out of Scope (YAGNI)

- tracky-mouse's head-tilt (3D pose) blending — its `headTrackingTiltInfluence`
  defaults to 0, i.e. off, and it carries a second calibration surface
  (yaw/pitch ranges and offsets).
- Its dwell-clicking system — we have the gesture system for clicks.
- Its `OneEuroFilter` — only used there for head tilt, which we are not
  porting.
- Adding points by clicking the preview, and the debug point/acceleration
  overlays.
- Any change to gestures, the tray, hotkeys, or the single-instance guard.
