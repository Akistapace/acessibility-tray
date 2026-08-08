# FaceMesh Mouse — Optical-Flow Tracking — Design Spec

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

This spec replaces that with a different pipeline: many points tracked by
optical flow and averaged, a power-curve acceleration instead of an EMA,
and per-axis sensitivity.

## Why This Approach Is Steadier

Three mechanisms, each addressing a different failure of the single-landmark
approach:

1. **Averaging many points instead of trusting one.** Seed points on the
   face and track them with Lucas-Kanade optical flow, then take the
   arithmetic mean of every surviving point's frame-to-frame delta. A single
   landmark's inference noise is uncorrelated across points, so averaging
   N points cuts it roughly by √N. This is where the *consistency* comes
   from.
2. **A power-curve acceleration instead of a smoothing filter.** A curve
   that shrinks small movements hard (so holding still is genuinely still,
   and fine positioning is possible) while leaving large movements fast.
   Unlike an EMA it introduces **no latency** — each frame's output depends
   only on that frame's input. This is where the *fluidity* comes from.
3. **Optical flow is temporally coherent.** Landmarks are re-inferred from
   scratch each frame; optical flow follows actual image texture from the
   previous frame, so its deltas don't carry per-frame re-detection jumps.

## Pipeline

### Point tracking (`point_tracker.py`, new)

**Seeding.** Each frame with a detected face, offer several landmark
positions as candidate points, drawn only from rigid parts of the face
(nose bridge and tip, nostrils, temples, cheek edges) — deliberately never
the mouth, eyebrows, or eyelids, which move during gestures and would jerk
the cursor mid-click. A candidate is **rejected only if an existing point
is already within a small fraction of the tracked head's size on BOTH
axes** — i.e. genuinely nearby. Rejecting on either axis alone would
discard symmetric features, which share a coordinate (the two nostrils sit
at the same height, the midline points share an x). Preferring
already-tracked points over fresh ones is deliberate: an established point
already carries motion history, and adding a near-duplicate would displace
it during pruning. Thresholds scale with head size (a fraction of it,
rather than a fixed pixel count) so the same relative behavior holds
whether the user sits close to the camera or farther back.

**Tracking.** `cv2.calcOpticalFlowPyrLK` on the grayscale frame, with a
tight minimum-eigenvalue threshold (well below OpenCV's own default) so
low-texture, unreliable tracks get rejected rather than admitted and left
to wander.

**Pruning**, in this order every frame:

- Drop points optical flow reports as lost (`status != 1`).
- **De-duplicate on a spatial grid** sized as a small fraction of head
  size: points are bucketed and one survivor is kept per bucket. Collapsed
  points contribute nothing, and clusters would weight one part of the
  face more heavily than the rest.
- **Cull points that have drifted off the face**: drop any point farther
  from the nose tip than the head size, measured on an ellipse stretched
  horizontally to match the average adult face's height/width ratio
  (`head_size` itself is the outer-eye-corner distance — landmarks `33`
  and `263`).

**Movement.** `get_movement()` returns the arithmetic mean of
`current - previous` across surviving points, in camera pixels, or
`(0.0, 0.0)` when no points survive.

**Pruning must run before the movement is read, every frame.** This
ordering is load-bearing, not incidental. A trial run of
`cv2.calcOpticalFlowPyrLK` on a synthetic translated image showed two of
three points recovering the true `(7, -4)` translation exactly while the
third diverged to `(-50, +73)` — and optical flow reported `status == 1`
for that point anyway. Its lost-point flag cannot be trusted on its own.
That single outlier dragged the mean of three points to `(-12, +22)`,
i.e. the wrong direction on both axes. The region cull is what catches it:
the diverged point landed ~188 px from the nose against a ~60 px head
size, far outside the ellipse. Reading movement before culling, or
dropping the cull as redundant with `status`, reintroduces exactly the
jitter this pipeline exists to remove.

The mean is outlier-sensitive by construction; the pipeline's answer is
to remove outliers before averaging (status filter, then grid
de-duplication, then region cull) and to track enough points that any
survivor's influence is small.

### Cursor mapping (`mouse_controller.py`)

Per active frame:

```
movement_x, movement_y = point_tracker.get_movement()   # camera pixels

delta_x = accelerate(movement_x * sensitivity_x, acceleration)
delta_y = accelerate(movement_y * sensitivity_y, acceleration)

if abs(delta_x * screen_w) < motion_threshold_px: delta_x = 0.0
if abs(delta_y * screen_h) < motion_threshold_px: delta_y = 0.0

cursor_x += delta_x * screen_w
cursor_y += delta_y * screen_h
clamp to screen bounds
```

where the acceleration curve is a power curve around a reference
magnitude: below it the delta shrinks, above it the delta grows, and at
`acceleration = 0` the curve is a flat pass-through (gain of 1
everywhere):

```python
def accelerate(delta: float, acceleration: float, reference: float = 0.05) -> float:
    magnitude = abs(delta)
    if magnitude < 1e-9:
        return 0.0
    gain = (magnitude / reference) ** acceleration
    return delta * gain
```

The reference value is derived from measuring real head-tracking output at
the default sensitivity: holding still produces deltas around 0.02–0.03,
deliberate movement produces 0.15 or more, so `0.05` cleanly separates the
two regimes.

Both axes **add**. `FaceTracker.process` mirrors the frame before FaceMesh
runs and returns the mirrored frame, which is what the point tracker
consumes, so the user's right is already `+x` — the same convention
`mouth_shift_ratio` is documented against. An earlier draft of this pipeline
subtracted on x (correct only for an *unmirrored* frame) and sent the
cursor the wrong way; the fix and a regression test that crosses the actual
mirroring boundary are documented in the git history for `mouse_controller.py`.

The motion threshold is applied **after** acceleration, matching a common
convention in pointer-acceleration implementations (e.g. eViacam's "Motion
Threshold"): that way the setting's unit is honestly "screen pixels of
cursor movement", not "pixels before a curve is applied to them".

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

Vertical sensitivity is twice horizontal because heads travel less
vertically than horizontally.

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

## Testing

- **`accelerate`** — pure: zero in gives zero out; sign is preserved;
  `acceleration=0` reduces to a linear pass-through (gain of 1 everywhere);
  a higher acceleration shrinks a small delta more than a large one
  (the property the whole curve exists for).
- **Pruning** — pure given synthetic point arrays: lost points dropped;
  two points sharing a grid bucket collapse to one; a point beyond the
  head-size ellipse is culled while one inside is kept; the horizontal
  stretch is asserted by a point that survives vertically but not at the
  same horizontal distance.
- **Seeding** — a candidate within the minimum distance of an existing
  point on both axes is rejected; one farther out on both axes, or level
  with an existing point on only one axis, is accepted.
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

- Head-tilt (3D pose) based cursor control — nose-tip/point-tracking
  position only, per the v1 spec's existing scope.
- A dwell-clicking system — the gesture system already covers clicks.
- A one-euro-style adaptive filter — the acceleration curve already covers
  the stability/responsiveness tradeoff without added latency.
- Adding points by clicking the preview, and debug point/acceleration
  overlays.
- Any change to gestures, the tray, hotkeys, or the single-instance guard.
