# FaceMesh Mouse — Gesture Expansion & Modern UI — Design Spec

**Date:** 2026-08-07
**Status:** Approved
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (v1),
`2026-08-05-usability-anchor-mode-design.md` (v2),
`2026-08-06-single-instance-background-startup-design.md` (v3)

## Purpose

Four problems with the current gesture set and config UI:

1. **Eyebrow raise can't distinguish sides.** `eyebrow_raise_ratio` averages
   both eyebrows, so raising only the left or only the right can't be
   mapped to different actions.
2. **Natural blinking fires unwanted clicks.** A gesture fires on the first
   frame its condition is true. A natural blink (~100–150ms) closes both
   eyes, but rarely in perfect sync — the 1–2 frames where only one eye is
   below threshold satisfy the single-eye condition and fire a click the
   user never intended.
3. **Too few distinct gestures.** Only 5 exist, and the user wants
   closed-mouth lateral movement (mouth pushed to the left / to the right)
   as two more control inputs.
4. **The config window looks dated.** Plain `ttk` widgets, and the layout
   won't hold 9 gesture rows without becoming unusable.

This spec covers: splitting the eyebrow metric per side, a per-gesture
hold-time requirement that filters out involuntary expressions, two new
closed-mouth lateral gestures, and a CustomTkinter rebuild of the config
window.

## Gesture Roster

Nine gestures, replacing the current five:

| Name | Condition (given per-gesture `threshold`) |
|---|---|
| `blink_a` | `ear_a < threshold and ear_b >= threshold` |
| `blink_b` | `ear_b < threshold and ear_a >= threshold` |
| `blink_both` | `ear_a < threshold and ear_b < threshold` |
| `eyebrow_a` | `eyebrow_raise_a > threshold and eyebrow_raise_b <= threshold` |
| `eyebrow_b` | `eyebrow_raise_b > threshold and eyebrow_raise_a <= threshold` |
| `eyebrow_both` | `eyebrow_raise_a > threshold and eyebrow_raise_b > threshold` |
| `mouth_open` | `mouth_open_ratio > threshold` |
| `mouth_left` | `mouth_shift_ratio < -threshold and mouth_open_ratio <= MOUTH_CLOSED_MAX` |
| `mouth_right` | `mouth_shift_ratio > threshold and mouth_open_ratio <= MOUTH_CLOSED_MAX` |

`blink_left`/`blink_right` are renamed to `blink_a`/`blink_b` so every
side-ambiguous gesture uses the same A/B convention (the existing GUI
already labels them "Piscar olho A"/"Piscar olho B" — this makes the
internal names match what the user sees). `eyebrow_raised` is replaced by
the three eyebrow gestures.

`MOUTH_CLOSED_MAX` is a module constant in `gestures.py` (`0.15`), not a
per-gesture config field: it answers "is the mouth closed enough for a
lateral gesture to count", which is a property of the detector, not
something the user tunes per gesture.

## New and Changed Metrics

`FaceMetrics` (in `tracker.py`) changes from:

```
nose_x, nose_y, ear_a, ear_b, mouth_open_ratio, eyebrow_raise_ratio, landmarks
```

to:

```
nose_x, nose_y, ear_a, ear_b, mouth_open_ratio,
eyebrow_raise_a, eyebrow_raise_b, mouth_shift_ratio, landmarks
```

### Eyebrow split

Current code computes both per-side distances and then averages them. The
change is to stop averaging — same landmarks, same normalization by face
height:

```python
eyebrow_raise_a = _dist(pts[EYEBROW_A], pts[EYELID_TOP_A]) / face_height
eyebrow_raise_b = _dist(pts[EYEBROW_B], pts[EYELID_TOP_B]) / face_height
```

Because each side's value is close to the previous average of the two, the
existing `0.15` threshold carries over unchanged as the default for all
three eyebrow gestures.

### Closed-mouth lateral shift

The naive measure — mouth-center x minus nose-tip x — is unusable here:
the user turns their head constantly to move the cursor, and the nose tip
protrudes, so it shifts more than the mouth under head yaw (parallax).
That would fire lateral-mouth gestures every time the user looks sideways.

Instead, measure the **signed perpendicular distance from the face's own
midline**, normalized by face width:

- **Midline axis:** landmark `168` (nose bridge, between the eyes) →
  landmark `152` (chin bottom). Both sit on the facial midline and are
  close to the face plane, so the axis rotates with the head instead of
  sliding under yaw or roll.
- **Measured point:** mouth center = midpoint of landmarks `61` and `291`
  (the mouth corners).
- **Normalizer:** `_dist(pts[33], pts[263])` — outer eye corners. Stable
  under mouth movement, unlike using the mouth's own width.

```python
def signed_lateral_offset(point, axis_start, axis_end) -> float:
    """Signed perpendicular distance from `point` to the line through
    axis_start -> axis_end. Positive = the +x side of the axis."""
    ax, ay = axis_start
    bx, by = axis_end
    px, py = point
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5 or 1e-6
    return ((px - ax) * dy - (py - ay) * dx) / length


mouth_shift_ratio = signed_lateral_offset(mouth_center, pts[168], pts[152]) / face_width
```

**Sign convention:** the chin is below the bridge in image coordinates
(`dy > 0`), so a mouth center at higher x yields a positive value. The
tracker mirrors the frame (`cv2.flip(frame, 1)`) *before* running FaceMesh,
so landmark coordinates are already in mirror space — higher x is the
user's own right. Therefore **positive = mouth pushed to the user's right**
(`mouth_right`), negative = to their left (`mouth_left`). Unlike the
eyes' A/B labels, this direction is determined rather than ambiguous, so
these two gestures are labeled "esquerda"/"direita" in the GUI and match
what the user sees in the mirrored preview.

Default threshold: `0.05` (5% of eye-to-eye distance). The GUI's live bar
plus the `threshold` field in `config.json` cover tuning if that proves
off for a given face.

## Hold Time (the natural-blink filter)

New per-gesture config field `hold_ms: int`, default `400` for every
gesture. A gesture fires only after its condition has been **continuously
true for `hold_ms`**, and fires at most once per hold — releasing the
condition rearms it.

`GestureEngine`'s per-gesture state changes from `(active, last_fired_at)`
to:

```python
@dataclass
class _GestureState:
    met_since: float | None = None   # when the condition last became true
    fired_this_hold: bool = False
    last_fired_at: float = -1e9
```

Per frame, per gesture:

- Condition false → reset `met_since = None`, `fired_this_hold = False`.
- Condition true and `met_since is None` → `met_since = now`.
- Condition true, `fired_this_hold` → nothing (already fired this hold).
- Condition true, held less than `hold_ms` → nothing yet.
- Condition true, held at least `hold_ms` → fire if the `cooldown_ms`
  window has elapsed; set `fired_this_hold = True` either way (so a
  cooldown-blocked hold doesn't retry every frame until released).

A natural blink lasts ~100–150ms total, and the asymmetric window where
only one eye is below threshold is a fraction of that — far under the
400ms default, so it never fires. A deliberate wink, held, does. The same
mechanism protects every other gesture from momentary facial noise
(talking, laughing, an eyebrow twitch).

`hold_ms = 0` disables the requirement, restoring the current
fire-immediately behavior.

`cooldown_ms` is kept and unchanged — it still rate-limits repeated
deliberate gestures, which is a different job from filtering involuntary
ones.

## Shared Trigger-Progress Function

The GUI needs "how close is this gesture to firing" for its live bars.
Today it duplicates threshold math inline, which already caused one bug
(the blink bars filled backwards until it was fixed). Instead,
`gestures.py` exposes a pure function used by both the engine's display
path and the GUI:

```python
def trigger_progress(name: str, metrics: FaceMetrics, threshold: float) -> float:
    """0.0 = far from triggering, 1.0 = at or past the trigger point."""
```

- Gestures that fire **above** a threshold (`mouth_open`, the eyebrows,
  the lateral-mouth pair on their respective signed side):
  `clamp(value / threshold, 0, 1)`.
- Gestures that fire **below** a threshold (the blinks):
  `clamp(threshold / max(value, 1e-6), 0, 1)` — this reads ~0.7 at rest
  (eyes open, EAR ≈ 0.30 vs. threshold 0.21) and reaches exactly 1.0 at
  the trigger point, so "fuller = closer to firing" holds uniformly across
  all nine bars.

Being pure and independent of Tk, this is unit-tested directly.

## Config Schema Changes

- `GESTURE_NAMES` becomes the nine names above.
- `GestureConfig` gains `hold_ms: int = 400`, loaded/saved/merged exactly
  like the existing `threshold`/`cooldown_ms` fields.
- Per-gesture defaults (`DEFAULT_ACTIONS`, `DEFAULT_THRESHOLDS`,
  `DEFAULT_COOLDOWN_MS`, new `DEFAULT_HOLD_MS`) are extended to nine
  entries. Default action mapping: `blink_a` → left click, `blink_b` →
  right click, `mouth_open` → double click, everything else → `none`
  (the user maps what they want; defaults stay conservative).
- **Migration.** `load_config` renames on read: `blink_left` → `blink_a`,
  `blink_right` → `blink_b`, `eyebrow_raised` → `eyebrow_both`. For each
  pair, the old key's saved settings are used as the source for the new
  gesture only when the new key isn't already present in the file. Existing
  `config.json` files keep working with the user's mappings intact instead
  of silently resetting to defaults.

## Config GUI Rebuild (CustomTkinter)

### Why CustomTkinter

`ctk.CTk` subclasses `tk.Tk`, so `root.after`, `root.withdraw`,
`root.deiconify`, and the single Tk mainloop keep working untouched — which
matters because the tray thread, the global hotkeys, the single-instance
socket listener, and the skip-wizard startup path all depend on that exact
mechanism. It's pure Python over Tk, so PyInstaller stays simple and the
bundle barely grows. Qt would mean rewriting `main.py`'s whole
threading/event-loop model and adding tens of megabytes; `ttkbootstrap`
would only re-theme the same `ttk` widgets.

### Layout

Dark appearance mode by default (`ctk.set_appearance_mode("dark")`).

- **Left column (always visible):** the live webcam preview, scaled to
  480×360, with the nose-tip overlay; below it, the primary
  "▶ Iniciar controle do mouse" button.
- **Right column:** a `CTkTabview` with three tabs. Nine gesture rows plus
  calibration controls no longer fit in one scrolling column, and tabs keep
  each task on one screen.
  - **Movimento** — the four play/pause capture toggles, the recording
    guide line and live extreme readout, and the deadzone and sensitivity
    sliders (all behavior unchanged from v2, restyled).
  - **Gestos** — nine rows, each: gesture label · live `CTkProgressBar`
    (driven by `trigger_progress`) · action `CTkOptionMenu` · hold-time
    `CTkSlider` (0–1000ms) with a live "N ms" label.
  - **Ajuda** — the contextual help text that currently sits inline under
    each step: what the A/B labels mean, how hold time filters accidental
    gestures, and the `Ctrl+Alt+P` "lift the mouse" pause/resume
    explanation.

### Preview rendering

The preview stays a standard `tk.Label` fed by `ImageTk.PhotoImage`, inside
a `CTkFrame`. CustomTkinter's `CTkImage` builds a separate `PhotoImage` for
light and dark mode on every construction, which is wasted work 30 times a
second for a video feed; mixing a plain Tk widget in is supported and is
the cheaper path here.

### Preview loop gating

`_tick` currently runs its full copy → `cvtColor` → PIL → `PhotoImage`
pipeline every 33ms for the entire process lifetime, including while the
window is hidden. Since v3's skip-wizard change made "hidden" the normal
state for the whole session, `_tick` now checks `winfo_viewable()` first
and skips the image work (still rescheduling itself) when the window isn't
on screen.

### File split

`config_gui.py` is already 416 lines and this adds a tab container and nine
richer gesture rows. It splits into three files with one responsibility
each:

- `config_gui.py` — window shell: root setup, preview, tab container,
  start button, save/hide lifecycle.
- `calibration_panel.py` — the Movimento tab: capture toggles, recording
  state, deadzone/sensitivity sliders.
- `gesture_panel.py` — the Gestos tab: the nine rows, their bars, action
  menus, and hold sliders.

Each panel takes the shared `AppConfig` and exposes a `frame` to place plus
an `update(metrics)` called from the shell's `_tick`.

## Packaging

`customtkinter` ships theme JSON and font assets that PyInstaller's static
analysis misses, so the documented build command gains
`--collect-data customtkinter`:

```
pyinstaller --onefile --windowed --paths src ^
  --collect-data mediapipe --collect-all cv2 --collect-data customtkinter ^
  -n facemesh-mouse run.py
```

`customtkinter` is added to `requirements.txt`.

## Testing

Pure logic, unit-tested with pytest (no camera, display, or OS mouse):

- **`signed_lateral_offset`** — synthetic points: a point on the axis
  returns ~0; points equidistant on either side return equal magnitudes
  with opposite signs; the result is unchanged when the axis is rotated
  (confirming yaw/roll tolerance, the property the whole approach rests
  on).
- **Hold-time state machine** (`GestureEngine` with the existing
  `FakeClock`): a condition true for less than `hold_ms` never fires; held
  past `hold_ms` fires exactly once; staying held doesn't refire; release
  and re-hold fires again; `hold_ms = 0` fires immediately.
- **Natural-blink scenario specifically:** a synthetic frame sequence where
  `ear_a` dips below threshold ~80ms before `ear_b` does (both then
  release), asserting `blink_a` does not fire — this is the exact failure
  the user reported.
- **`trigger_progress`** — above-threshold and below-threshold families
  both reach 1.0 at the trigger point and stay within `[0, 1]`.
- **Config** — nine gestures present with defaults; `hold_ms` round-trips;
  each of the three legacy names migrates its settings to the new name;
  a file that already has the new key is not overwritten by the legacy one.
- **The three GUI files** — manual checklist only, consistent with every
  prior spec: launch, confirm each tab renders, confirm the nine bars react
  to the corresponding real expressions, confirm a natural blink fires
  nothing while a held wink does, confirm capture/sliders still work.

## Out of Scope (YAGNI)

- Additional expressions beyond the nine (smile, cheek puff, head tilt as
  a discrete gesture).
- Per-gesture threshold editing in the GUI — thresholds stay
  `config.json`-only, as they are today; the live bars make it visible
  when one needs adjusting.
- A visual countdown of hold progress while a gesture is being held (the
  bar reaching full plus the action firing is feedback enough for v1 of
  this feature).
- Light/dark theme toggle in the UI — dark is the default and only mode
  shipped.
- Replacing `pystray` with a Qt/CTk-native tray, or any change to the tray,
  hotkey, engine, or mouse-control modules.
