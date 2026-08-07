# Gesture Expansion & Modern UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nine gestures instead of five (eyebrow raise split per side, closed-mouth lateral shift added), a per-gesture hold-time requirement so natural blinks stop firing spurious clicks, and a CustomTkinter rebuild of the config window.

**Architecture:** `tracker.py` stops averaging the two eyebrow distances and adds a yaw-tolerant lateral-mouth metric (signed perpendicular distance from the face midline). `gestures.py` grows to nine conditions, gains a hold-time state machine (`met_since` / `fired_this_hold`), and exposes a pure `trigger_progress` the GUI reuses for its live bars. `config.py` carries the nine names plus `hold_ms`, and migrates legacy gesture keys on load. The GUI is rebuilt on CustomTkinter and split into a shell (`config_gui.py`) plus two panels (`calibration_panel.py`, `gesture_panel.py`).

**Tech Stack:** Python 3.11, customtkinter 6.0.0 (new dependency, already installed and API-verified in `.venv`), OpenCV, MediaPipe, Pillow, pytest.

## Global Constraints

- UI-facing strings stay in Portuguese, matching the existing labels.
- Every module keeps `from __future__ import annotations` as its first import.
- Run tests with `.venv\Scripts\python -m pytest tests/ -v` (repo root). `pyproject.toml` sets `pythonpath = ["src"]`.
- The app must remain runnable after every task — no task may leave `run.py` raising on startup.
- `ctk.CTk` subclasses `tk.Tk`; `root.after` / `root.withdraw` / `root.deiconify` / `root.winfo_viewable` must keep working, because the tray thread, global hotkeys, the single-instance socket listener, and the skip-wizard startup path all depend on them. Do not restructure the Tk event loop or the threading model.
- Gesture threshold values stay `config.json`-only — no threshold editors in the GUI.
- Do not modify `engine.py`, `mouse_controller.py`, `tray.py`, `hotkeys.py`, or `single_instance.py`. Only `main.py`'s root creation changes, in Task 5.
- `customtkinter==6.0.0` is the verified version. `CTk`, `CTkTabview`, `CTkProgressBar`, `CTkOptionMenu`, `CTkSlider`, `CTkFrame`, `CTkLabel`, `CTkButton`, `CTkScrollableFrame`, `set_appearance_mode`, and `set_default_color_theme` all exist and were smoke-tested in this venv.

---

### Task 1: Tracker metrics — split eyebrows, add lateral-mouth measure

**Files:**
- Modify: `src/facemesh_mouse/tracker.py`
- Modify: `src/facemesh_mouse/gestures.py` (one line — transitional, keeps behavior identical)
- Modify: `src/facemesh_mouse/config_gui.py` (one line — transitional, keeps display identical)
- Modify: `tests/test_gestures.py`, `tests/test_engine.py`, `tests/test_mouse_controller.py` (their `_metrics` helpers)
- Test: `tests/test_tracker.py` (new file)

**Interfaces:**
- Produces: `FaceMetrics` with `eyebrow_raise_a: float`, `eyebrow_raise_b: float`, and `mouth_shift_ratio: float` replacing `eyebrow_raise_ratio`; module-level `signed_lateral_offset(point, axis_start, axis_end) -> float` where each argument is an `(x, y)` tuple.
- Consumes: nothing new.

This task keeps the existing five gestures behaving exactly as before — the eyebrow condition and the GUI bar switch to averaging the two new fields, which reproduces the old single field. The nine-gesture change lands in Task 2.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tracker.py`:

```python
import math

import pytest

from facemesh_mouse.tracker import signed_lateral_offset


def test_signed_lateral_offset_is_zero_on_the_axis():
    assert signed_lateral_offset((0.5, 0.7), (0.5, 0.3), (0.5, 0.9)) == pytest.approx(0.0)


def test_signed_lateral_offset_is_symmetric_around_the_axis():
    axis_start, axis_end = (0.5, 0.3), (0.5, 0.9)
    higher_x = signed_lateral_offset((0.6, 0.7), axis_start, axis_end)
    lower_x = signed_lateral_offset((0.4, 0.7), axis_start, axis_end)

    assert higher_x > 0
    assert lower_x < 0
    assert higher_x == pytest.approx(-lower_x)


def test_signed_lateral_offset_magnitude_matches_perpendicular_distance():
    # point sits 0.1 to the right of a vertical axis
    offset = signed_lateral_offset((0.6, 0.7), (0.5, 0.3), (0.5, 0.9))
    assert offset == pytest.approx(0.1)


def test_signed_lateral_offset_survives_rotation():
    """Head yaw/roll rotates the whole face. Rotating the axis and the point
    together must not change the measured offset -- this is the property the
    lateral-mouth gesture depends on to not fire when the user turns their
    head to move the cursor."""
    axis_start = (0.5, 0.3)
    axis_end = (0.5, 0.9)
    point = (0.6, 0.7)
    before = signed_lateral_offset(point, axis_start, axis_end)

    def rotate(p, origin, angle):
        ox, oy = origin
        dx, dy = p[0] - ox, p[1] - oy
        return (
            ox + dx * math.cos(angle) - dy * math.sin(angle),
            oy + dx * math.sin(angle) + dy * math.cos(angle),
        )

    angle = math.radians(25)
    after = signed_lateral_offset(
        rotate(point, axis_start, angle),
        axis_start,
        rotate(axis_end, axis_start, angle),
    )

    assert after == pytest.approx(before)


def test_signed_lateral_offset_degenerate_axis_does_not_divide_by_zero():
    result = signed_lateral_offset((0.6, 0.7), (0.5, 0.5), (0.5, 0.5))
    assert math.isfinite(result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_tracker.py -v`
Expected: FAIL with `ImportError: cannot import name 'signed_lateral_offset' from 'facemesh_mouse.tracker'`

- [ ] **Step 3: Add the landmark constants and the pure function**

In `src/facemesh_mouse/tracker.py`, replace:

```python
NOSE_TIP = 1
FOREHEAD_TOP = 10
CHIN_BOTTOM = 152
```

with:

```python
NOSE_TIP = 1
FOREHEAD_TOP = 10
CHIN_BOTTOM = 152

# Facial midline: the nose bridge (between the eyes) down to the chin. Both
# points sit on the midline and close to the face plane, so the axis they
# define rotates with the head instead of sliding under yaw -- which is what
# makes the lateral-mouth measure survive the constant head turning this app
# uses to move the cursor.
FACE_AXIS_TOP = 168

# Outer eye corners, used as a mouth-movement-independent face width.
EYE_OUTER_A = 33
EYE_OUTER_B = 263
```

Then, after the `_eye_aspect_ratio` function, add:

```python
def signed_lateral_offset(point, axis_start, axis_end) -> float:
    """Signed perpendicular distance from `point` to the line through
    `axis_start` -> `axis_end`. Positive means the point lies on the higher-x
    side of the axis. All arguments are (x, y) tuples."""
    ax, ay = axis_start
    bx, by = axis_end
    px, py = point
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5 or 1e-6
    return ((px - ax) * dy - (py - ay) * dx) / length
```

- [ ] **Step 4: Update the `FaceMetrics` dataclass**

In `src/facemesh_mouse/tracker.py`, replace:

```python
@dataclass
class FaceMetrics:
    nose_x: float
    nose_y: float
    ear_a: float
    ear_b: float
    mouth_open_ratio: float
    eyebrow_raise_ratio: float
    landmarks: list  # raw (x, y) normalized points, for preview overlay only
```

with:

```python
@dataclass
class FaceMetrics:
    nose_x: float
    nose_y: float
    ear_a: float
    ear_b: float
    mouth_open_ratio: float
    eyebrow_raise_a: float
    eyebrow_raise_b: float
    mouth_shift_ratio: float  # signed; positive = mouth pushed to the user's right
    landmarks: list  # raw (x, y) normalized points, for preview overlay only
```

- [ ] **Step 5: Compute the new metrics in `process`**

In `src/facemesh_mouse/tracker.py`, replace:

```python
        face_height = _dist(pts[FOREHEAD_TOP], pts[CHIN_BOTTOM]) or 1e-6

        ear_a = _eye_aspect_ratio([pts[i] for i in EYE_A])
        ear_b = _eye_aspect_ratio([pts[i] for i in EYE_B])

        mouth_vertical = _dist(pts[MOUTH_TOP_INNER], pts[MOUTH_BOTTOM_INNER])
        mouth_horizontal = _dist(pts[MOUTH_CORNER_LEFT], pts[MOUTH_CORNER_RIGHT]) or 1e-6
        mouth_open_ratio = mouth_vertical / mouth_horizontal

        eyebrow_dist_a = _dist(pts[EYEBROW_A], pts[EYELID_TOP_A])
        eyebrow_dist_b = _dist(pts[EYEBROW_B], pts[EYELID_TOP_B])
        eyebrow_raise_ratio = ((eyebrow_dist_a + eyebrow_dist_b) / 2.0) / face_height

        metrics = FaceMetrics(
            nose_x=pts[NOSE_TIP][0],
            nose_y=pts[NOSE_TIP][1],
            ear_a=ear_a,
            ear_b=ear_b,
            mouth_open_ratio=mouth_open_ratio,
            eyebrow_raise_ratio=eyebrow_raise_ratio,
            landmarks=pts,
        )
        return frame_bgr, metrics
```

with:

```python
        face_height = _dist(pts[FOREHEAD_TOP], pts[CHIN_BOTTOM]) or 1e-6
        face_width = _dist(pts[EYE_OUTER_A], pts[EYE_OUTER_B]) or 1e-6

        ear_a = _eye_aspect_ratio([pts[i] for i in EYE_A])
        ear_b = _eye_aspect_ratio([pts[i] for i in EYE_B])

        mouth_vertical = _dist(pts[MOUTH_TOP_INNER], pts[MOUTH_BOTTOM_INNER])
        mouth_horizontal = _dist(pts[MOUTH_CORNER_LEFT], pts[MOUTH_CORNER_RIGHT]) or 1e-6
        mouth_open_ratio = mouth_vertical / mouth_horizontal

        eyebrow_raise_a = _dist(pts[EYEBROW_A], pts[EYELID_TOP_A]) / face_height
        eyebrow_raise_b = _dist(pts[EYEBROW_B], pts[EYELID_TOP_B]) / face_height

        mouth_center = (
            (pts[MOUTH_CORNER_LEFT][0] + pts[MOUTH_CORNER_RIGHT][0]) / 2.0,
            (pts[MOUTH_CORNER_LEFT][1] + pts[MOUTH_CORNER_RIGHT][1]) / 2.0,
        )
        mouth_shift_ratio = (
            signed_lateral_offset(mouth_center, pts[FACE_AXIS_TOP], pts[CHIN_BOTTOM])
            / face_width
        )

        metrics = FaceMetrics(
            nose_x=pts[NOSE_TIP][0],
            nose_y=pts[NOSE_TIP][1],
            ear_a=ear_a,
            ear_b=ear_b,
            mouth_open_ratio=mouth_open_ratio,
            eyebrow_raise_a=eyebrow_raise_a,
            eyebrow_raise_b=eyebrow_raise_b,
            mouth_shift_ratio=mouth_shift_ratio,
            landmarks=pts,
        )
        return frame_bgr, metrics
```

- [ ] **Step 6: Keep the existing eyebrow gesture behaving identically**

In `src/facemesh_mouse/gestures.py`, replace:

```python
    if name == "eyebrow_raised":
        return metrics.eyebrow_raise_ratio > threshold
```

with:

```python
    if name == "eyebrow_raised":
        # Transitional: reproduces the old averaged metric. Task 2 replaces
        # this gesture with per-side eyebrow_a / eyebrow_b / eyebrow_both.
        return (metrics.eyebrow_raise_a + metrics.eyebrow_raise_b) / 2.0 > threshold
```

- [ ] **Step 7: Keep the existing GUI bar showing the same value**

In `src/facemesh_mouse/config_gui.py`, inside `_update_metric_bars`, replace:

```python
            "eyebrow_raise_ratio": metrics.eyebrow_raise_ratio,
```

with:

```python
            "eyebrow_raise_ratio": (metrics.eyebrow_raise_a + metrics.eyebrow_raise_b) / 2.0,
```

- [ ] **Step 8: Update the three test `_metrics` helpers**

In `tests/test_gestures.py`, replace:

```python
def _metrics(ear_a=0.3, ear_b=0.3, mouth=0.1, eyebrow=0.05):
    return FaceMetrics(
        nose_x=0.5,
        nose_y=0.5,
        ear_a=ear_a,
        ear_b=ear_b,
        mouth_open_ratio=mouth,
        eyebrow_raise_ratio=eyebrow,
        landmarks=[],
    )
```

with:

```python
def _metrics(ear_a=0.3, ear_b=0.3, mouth=0.1, eyebrow=0.05, eyebrow_b=None, mouth_shift=0.0):
    return FaceMetrics(
        nose_x=0.5,
        nose_y=0.5,
        ear_a=ear_a,
        ear_b=ear_b,
        mouth_open_ratio=mouth,
        eyebrow_raise_a=eyebrow,
        eyebrow_raise_b=eyebrow if eyebrow_b is None else eyebrow_b,
        mouth_shift_ratio=mouth_shift,
        landmarks=[],
    )
```

In `tests/test_engine.py`, replace:

```python
def _metrics(nose_x=0.5, nose_y=0.5):
    return FaceMetrics(
        nose_x=nose_x,
        nose_y=nose_y,
        ear_a=0.3,
        ear_b=0.3,
        mouth_open_ratio=0.1,
        eyebrow_raise_ratio=0.05,
        landmarks=[],
    )
```

with:

```python
def _metrics(nose_x=0.5, nose_y=0.5):
    return FaceMetrics(
        nose_x=nose_x,
        nose_y=nose_y,
        ear_a=0.3,
        ear_b=0.3,
        mouth_open_ratio=0.1,
        eyebrow_raise_a=0.05,
        eyebrow_raise_b=0.05,
        mouth_shift_ratio=0.0,
        landmarks=[],
    )
```

In `tests/test_mouse_controller.py`, replace:

```python
def _metrics(nose_x=0.5, nose_y=0.5):
    return FaceMetrics(
        nose_x=nose_x,
        nose_y=nose_y,
        ear_a=0.3,
        ear_b=0.3,
        mouth_open_ratio=0.1,
        eyebrow_raise_ratio=0.05,
        landmarks=[],
    )
```

with:

```python
def _metrics(nose_x=0.5, nose_y=0.5):
    return FaceMetrics(
        nose_x=nose_x,
        nose_y=nose_y,
        ear_a=0.3,
        ear_b=0.3,
        mouth_open_ratio=0.1,
        eyebrow_raise_a=0.05,
        eyebrow_raise_b=0.05,
        mouth_shift_ratio=0.0,
        landmarks=[],
    )
```

- [ ] **Step 9: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 39 tests (34 existing + 5 new tracker tests)

- [ ] **Step 10: Verify the GUI still imports**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/config_gui.py src/facemesh_mouse/tracker.py src/facemesh_mouse/gestures.py`
Expected: no output, exit code 0

- [ ] **Step 11: Commit**

```bash
git add src/facemesh_mouse/tracker.py src/facemesh_mouse/gestures.py src/facemesh_mouse/config_gui.py tests/
git commit -m "feat(tracker): split eyebrow metric per side, add yaw-tolerant lateral mouth measure"
```

---

### Task 2: Nine gestures, hold time, trigger progress, config migration

**Files:**
- Modify: `src/facemesh_mouse/gestures.py`
- Modify: `src/facemesh_mouse/config.py`
- Modify: `src/facemesh_mouse/config_gui.py` (label/bar maps only — transitional, the full rebuild is Tasks 3-5)
- Test: `tests/test_gestures.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `FaceMetrics.eyebrow_raise_a/.eyebrow_raise_b/.mouth_shift_ratio` (Task 1).
- Produces:
  - `gestures.MOUTH_CLOSED_MAX: float = 0.15`
  - `gestures.trigger_progress(name: str, metrics: FaceMetrics, threshold: float) -> float` returning `0.0`–`1.0`
  - `config.GESTURE_NAMES` = `["blink_a", "blink_b", "blink_both", "eyebrow_a", "eyebrow_b", "eyebrow_both", "mouth_open", "mouth_left", "mouth_right"]`
  - `config.GestureConfig.hold_ms: int = 400`
  - `config.LEGACY_GESTURE_NAMES: dict[str, str]`

- [ ] **Step 1: Write the failing gesture tests**

Replace the whole body of `tests/test_gestures.py` below its imports (keep the `FakeClock` class and the `_metrics` helper from Task 1; replace `_config` and every test) with:

```python
def _config(hold_ms=0, **overrides):
    gestures = {
        "blink_a": GestureConfig(action="left_click", threshold=0.2, cooldown_ms=0, hold_ms=hold_ms),
        "blink_b": GestureConfig(action="right_click", threshold=0.2, cooldown_ms=0, hold_ms=hold_ms),
        "blink_both": GestureConfig(action="none", threshold=0.2, cooldown_ms=0, hold_ms=hold_ms),
        "eyebrow_a": GestureConfig(action="none", threshold=0.1, cooldown_ms=0, hold_ms=hold_ms),
        "eyebrow_b": GestureConfig(action="none", threshold=0.1, cooldown_ms=0, hold_ms=hold_ms),
        "eyebrow_both": GestureConfig(action="none", threshold=0.1, cooldown_ms=0, hold_ms=hold_ms),
        "mouth_open": GestureConfig(action="double_click", threshold=0.3, cooldown_ms=0, hold_ms=hold_ms),
        "mouth_left": GestureConfig(action="none", threshold=0.05, cooldown_ms=0, hold_ms=hold_ms),
        "mouth_right": GestureConfig(action="none", threshold=0.05, cooldown_ms=0, hold_ms=hold_ms),
    }
    gestures.update(overrides)
    return AppConfig(calibration=CalibrationConfig(), gestures=gestures)


def test_blink_a_fires_once_on_transition():
    engine = GestureEngine(_config(), clock=FakeClock())

    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_blink_both_takes_precedence_over_single_eye_condition():
    engine = GestureEngine(_config(), clock=FakeClock())
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.1)) == ["blink_both"]


def test_eyebrow_a_fires_alone_without_eyebrow_b():
    engine = GestureEngine(_config(), clock=FakeClock())
    assert engine.evaluate(_metrics(eyebrow=0.2, eyebrow_b=0.05)) == ["eyebrow_a"]


def test_eyebrow_both_requires_both_sides_raised():
    engine = GestureEngine(_config(), clock=FakeClock())
    assert engine.evaluate(_metrics(eyebrow=0.2, eyebrow_b=0.2)) == ["eyebrow_both"]


def test_mouth_left_and_right_are_direction_specific():
    engine = GestureEngine(_config(), clock=FakeClock())
    assert engine.evaluate(_metrics(mouth_shift=-0.2)) == ["mouth_left"]

    engine.evaluate(_metrics(mouth_shift=0.0))
    assert engine.evaluate(_metrics(mouth_shift=0.2)) == ["mouth_right"]


def test_lateral_mouth_gestures_require_a_closed_mouth():
    engine = GestureEngine(_config(), clock=FakeClock())

    # shifted far left, but the mouth is open -> not a closed-mouth gesture
    assert engine.evaluate(_metrics(mouth_shift=-0.2, mouth=0.5)) == ["mouth_open"]

    # same shift with the mouth closed does fire
    assert engine.evaluate(_metrics(mouth_shift=-0.2, mouth=0.05)) == ["mouth_left"]


def test_cooldown_blocks_rapid_retrigger():
    clock = FakeClock()
    engine = GestureEngine(
        _config(blink_a=GestureConfig(action="left_click", threshold=0.2, cooldown_ms=1000, hold_ms=0)),
        clock=clock,
    )

    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]

    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    clock.t = 0.5
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))
    clock.t = 1.1
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_natural_blink_does_not_fire_a_single_eye_gesture():
    """The reported bug: a natural blink closes both eyes slightly out of
    sync, and the asymmetric window used to satisfy blink_a immediately.
    With a hold time it must never fire."""
    clock = FakeClock()
    engine = GestureEngine(_config(hold_ms=400), clock=clock)

    clock.t = 0.0
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []  # eye A closes first

    clock.t = 0.08
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.1)) == []  # eye B follows 80ms later

    clock.t = 0.14
    assert engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3)) == []  # both reopen, ~140ms blink

    clock.t = 1.0
    assert engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3)) == []  # and nothing fires later


def test_deliberate_hold_fires_once_after_the_hold_time():
    clock = FakeClock()
    engine = GestureEngine(_config(hold_ms=400), clock=clock)

    clock.t = 0.0
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    clock.t = 0.399
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []

    clock.t = 0.400
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]

    clock.t = 0.900
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []  # no refire while held


def test_releasing_and_reholding_fires_again():
    clock = FakeClock()
    engine = GestureEngine(_config(hold_ms=400), clock=clock)

    clock.t = 0.0
    engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3))
    clock.t = 0.5
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]

    clock.t = 0.6
    engine.evaluate(_metrics(ear_a=0.3, ear_b=0.3))  # release

    clock.t = 0.7
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == []
    clock.t = 1.2
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_hold_ms_zero_fires_immediately():
    engine = GestureEngine(_config(hold_ms=0), clock=FakeClock())
    assert engine.evaluate(_metrics(ear_a=0.1, ear_b=0.3)) == ["blink_a"]


def test_trigger_progress_reaches_one_at_an_above_threshold_trigger():
    assert trigger_progress("mouth_open", _metrics(mouth=0.35), 0.35) == pytest.approx(1.0)


def test_trigger_progress_reaches_one_at_a_below_threshold_trigger():
    assert trigger_progress("blink_a", _metrics(ear_a=0.21), 0.21) == pytest.approx(1.0)


def test_trigger_progress_is_partial_at_rest_for_blinks():
    progress = trigger_progress("blink_a", _metrics(ear_a=0.30), 0.21)
    assert 0.0 < progress < 1.0


def test_trigger_progress_stays_in_the_unit_range():
    assert trigger_progress("blink_a", _metrics(ear_a=0.01), 0.21) == 1.0
    assert trigger_progress("mouth_open", _metrics(mouth=99.0), 0.35) == 1.0
    assert trigger_progress("mouth_left", _metrics(mouth_shift=0.5), 0.05) == 0.0


def test_trigger_progress_covers_every_gesture_name():
    metrics = _metrics()
    for name in config_mod.GESTURE_NAMES:
        value = trigger_progress(name, metrics, 0.2)
        assert 0.0 <= value <= 1.0
```

Replace the import block at the top of `tests/test_gestures.py` with:

```python
import pytest

from facemesh_mouse import config as config_mod
from facemesh_mouse.config import AppConfig, CalibrationConfig, GestureConfig
from facemesh_mouse.gestures import GestureEngine, trigger_progress
from facemesh_mouse.tracker import FaceMetrics
```

- [ ] **Step 2: Write the failing config tests**

Append to `tests/test_config.py`:

```python
def test_default_config_has_the_nine_gestures():
    cfg = config_mod.default_config()
    assert set(cfg.gestures) == {
        "blink_a",
        "blink_b",
        "blink_both",
        "eyebrow_a",
        "eyebrow_b",
        "eyebrow_both",
        "mouth_open",
        "mouth_left",
        "mouth_right",
    }


def test_hold_ms_defaults_and_round_trips(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    assert original.gestures["blink_a"].hold_ms == 400

    original.gestures["blink_a"].hold_ms = 250
    config_mod.save_config(path, original)

    assert config_mod.load_config(path).gestures["blink_a"].hold_ms == 250


def test_legacy_blink_names_migrate_to_the_a_b_names(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "gestures": {
                    "blink_left": {"action": "scroll_up"},
                    "blink_right": {"action": "scroll_down"},
                }
            }
        )
    )

    loaded = config_mod.load_config(path)

    assert loaded.gestures["blink_a"].action == "scroll_up"
    assert loaded.gestures["blink_b"].action == "scroll_down"


def test_legacy_eyebrow_raised_migrates_to_eyebrow_both(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gestures": {"eyebrow_raised": {"action": "scroll_up"}}}))

    loaded = config_mod.load_config(path)

    assert loaded.gestures["eyebrow_both"].action == "scroll_up"


def test_legacy_name_does_not_override_an_already_migrated_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "gestures": {
                    "eyebrow_raised": {"action": "scroll_up"},
                    "eyebrow_both": {"action": "double_click"},
                }
            }
        )
    )

    loaded = config_mod.load_config(path)

    assert loaded.gestures["eyebrow_both"].action == "double_click"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_gestures.py tests/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'trigger_progress'` and `TypeError: GestureConfig.__init__() got an unexpected keyword argument 'hold_ms'`

- [ ] **Step 4: Rewrite `gestures.py`**

Replace the entire contents of `src/facemesh_mouse/gestures.py` with:

```python
"""Edge-triggered gesture detection from per-frame face metrics.

Each gesture has a threshold, a hold time, and a cooldown. A gesture fires
once its condition has been continuously true for `hold_ms` -- which is what
keeps involuntary expressions (above all a natural blink, whose two eyes
close a few frames apart) from firing actions the user never intended. It
fires at most once per hold; releasing the condition rearms it. The cooldown
additionally rate-limits repeated deliberate gestures.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .config import AppConfig
from .tracker import FaceMetrics

# A lateral-mouth gesture only counts while the mouth is closed. This is a
# property of the detector rather than something the user tunes per gesture,
# so it is a constant instead of a config field.
MOUTH_CLOSED_MAX = 0.15

# Gestures whose condition is "metric fell BELOW the threshold". Everything
# else fires when its metric rises above it.
_FIRES_BELOW = {"blink_a", "blink_b", "blink_both"}


def _condition(name: str, metrics: FaceMetrics, threshold: float) -> bool:
    if name == "blink_a":
        return metrics.ear_a < threshold and metrics.ear_b >= threshold
    if name == "blink_b":
        return metrics.ear_b < threshold and metrics.ear_a >= threshold
    if name == "blink_both":
        return metrics.ear_a < threshold and metrics.ear_b < threshold
    if name == "eyebrow_a":
        return metrics.eyebrow_raise_a > threshold and metrics.eyebrow_raise_b <= threshold
    if name == "eyebrow_b":
        return metrics.eyebrow_raise_b > threshold and metrics.eyebrow_raise_a <= threshold
    if name == "eyebrow_both":
        return metrics.eyebrow_raise_a > threshold and metrics.eyebrow_raise_b > threshold
    if name == "mouth_open":
        return metrics.mouth_open_ratio > threshold
    if name == "mouth_left":
        return (
            metrics.mouth_shift_ratio < -threshold
            and metrics.mouth_open_ratio <= MOUTH_CLOSED_MAX
        )
    if name == "mouth_right":
        return (
            metrics.mouth_shift_ratio > threshold
            and metrics.mouth_open_ratio <= MOUTH_CLOSED_MAX
        )
    raise ValueError(f"Unknown gesture: {name}")


def _progress_value(name: str, metrics: FaceMetrics) -> float:
    """The single metric that governs how close `name` is to triggering.
    Where a gesture needs two sides to agree, the lagging side governs."""
    if name == "blink_a":
        return metrics.ear_a
    if name == "blink_b":
        return metrics.ear_b
    if name == "blink_both":
        return max(metrics.ear_a, metrics.ear_b)
    if name == "eyebrow_a":
        return metrics.eyebrow_raise_a
    if name == "eyebrow_b":
        return metrics.eyebrow_raise_b
    if name == "eyebrow_both":
        return min(metrics.eyebrow_raise_a, metrics.eyebrow_raise_b)
    if name == "mouth_open":
        return metrics.mouth_open_ratio
    if name == "mouth_left":
        return -metrics.mouth_shift_ratio
    if name == "mouth_right":
        return metrics.mouth_shift_ratio
    raise ValueError(f"Unknown gesture: {name}")


def trigger_progress(name: str, metrics: FaceMetrics, threshold: float) -> float:
    """How close `name` is to firing, as 0.0 (far) to 1.0 (at or past the
    trigger point). Shared with the config GUI's live bars so the display and
    the detector can never disagree about which direction means 'closer'."""
    value = _progress_value(name, metrics)
    threshold = threshold or 1e-6
    if name in _FIRES_BELOW:
        ratio = threshold / max(value, 1e-6)
    else:
        ratio = value / threshold
    return max(0.0, min(1.0, ratio))


@dataclass
class _GestureState:
    met_since: float | None = None  # when the condition last became true
    fired_this_hold: bool = False
    last_fired_at: float = -1e9


class GestureEngine:
    def __init__(self, config: AppConfig, clock=time.monotonic) -> None:
        self._config = config
        self._clock = clock
        self._state = {name: _GestureState() for name in config.gestures}

    def update_config(self, config: AppConfig) -> None:
        self._config = config
        for name in config.gestures:
            self._state.setdefault(name, _GestureState())

    def evaluate(self, metrics: FaceMetrics) -> list[str]:
        """Returns the list of gesture names that fired on this frame."""
        fired = []
        now = self._clock()
        for name, gesture_cfg in self._config.gestures.items():
            state = self._state[name]

            if not _condition(name, metrics, gesture_cfg.threshold):
                state.met_since = None
                state.fired_this_hold = False
                continue

            if state.met_since is None:
                state.met_since = now

            if state.fired_this_hold:
                continue

            if (now - state.met_since) * 1000.0 < gesture_cfg.hold_ms:
                continue

            if (now - state.last_fired_at) * 1000.0 >= gesture_cfg.cooldown_ms:
                fired.append(name)
                state.last_fired_at = now
            # Marked either way: a cooldown-blocked hold must not retry every
            # frame until the user releases the expression.
            state.fired_this_hold = True

        return fired
```

- [ ] **Step 5: Update `config.py`**

In `src/facemesh_mouse/config.py`, replace:

```python
GESTURE_NAMES = [
    "blink_left",
    "blink_right",
    "blink_both",
    "mouth_open",
    "eyebrow_raised",
]

DEFAULT_THRESHOLDS = {
    "blink_left": 0.21,
    "blink_right": 0.21,
    "blink_both": 0.21,
    "mouth_open": 0.35,
    "eyebrow_raised": 0.15,
}

DEFAULT_ACTIONS = {
    "blink_left": "left_click",
    "blink_right": "right_click",
    "blink_both": "none",
    "mouth_open": "double_click",
    "eyebrow_raised": "scroll_up",
}

DEFAULT_COOLDOWN_MS = {
    "blink_left": 400,
    "blink_right": 400,
    "blink_both": 400,
    "mouth_open": 600,
    "eyebrow_raised": 300,
}
```

with:

```python
GESTURE_NAMES = [
    "blink_a",
    "blink_b",
    "blink_both",
    "eyebrow_a",
    "eyebrow_b",
    "eyebrow_both",
    "mouth_open",
    "mouth_left",
    "mouth_right",
]

# Gesture names used by older config.json files, mapped to their current
# name. Migrated on load so an existing setup keeps its mappings.
LEGACY_GESTURE_NAMES = {
    "blink_left": "blink_a",
    "blink_right": "blink_b",
    "eyebrow_raised": "eyebrow_both",
}

DEFAULT_THRESHOLDS = {
    "blink_a": 0.21,
    "blink_b": 0.21,
    "blink_both": 0.21,
    "eyebrow_a": 0.15,
    "eyebrow_b": 0.15,
    "eyebrow_both": 0.15,
    "mouth_open": 0.35,
    "mouth_left": 0.05,
    "mouth_right": 0.05,
}

DEFAULT_ACTIONS = {
    "blink_a": "left_click",
    "blink_b": "right_click",
    "blink_both": "none",
    "eyebrow_a": "none",
    "eyebrow_b": "none",
    "eyebrow_both": "none",
    "mouth_open": "double_click",
    "mouth_left": "none",
    "mouth_right": "none",
}

DEFAULT_COOLDOWN_MS = {
    "blink_a": 400,
    "blink_b": 400,
    "blink_both": 400,
    "eyebrow_a": 400,
    "eyebrow_b": 400,
    "eyebrow_both": 400,
    "mouth_open": 600,
    "mouth_left": 400,
    "mouth_right": 400,
}

# How long a gesture's condition must hold before it fires. The default is
# comfortably above a natural blink (~100-150ms), which is what stops
# involuntary expressions from firing actions.
DEFAULT_HOLD_MS = {name: 400 for name in GESTURE_NAMES}
```

Then replace:

```python
@dataclass
class GestureConfig:
    action: str = "none"
    threshold: float = 0.2
    cooldown_ms: int = 400
```

with:

```python
@dataclass
class GestureConfig:
    action: str = "none"
    threshold: float = 0.2
    cooldown_ms: int = 400
    hold_ms: int = 400
```

Then replace:

```python
def default_config() -> AppConfig:
    gestures = {
        name: GestureConfig(
            action=DEFAULT_ACTIONS[name],
            threshold=DEFAULT_THRESHOLDS[name],
            cooldown_ms=DEFAULT_COOLDOWN_MS[name],
        )
        for name in GESTURE_NAMES
    }
    return AppConfig(calibration=CalibrationConfig(), gestures=gestures)


def _merge_gesture(name: str, raw: dict) -> GestureConfig:
    base = GestureConfig(
        action=DEFAULT_ACTIONS[name],
        threshold=DEFAULT_THRESHOLDS[name],
        cooldown_ms=DEFAULT_COOLDOWN_MS[name],
    )
    action = raw.get("action", base.action)
    if action not in VALID_ACTIONS:
        action = base.action
    return GestureConfig(
        action=action,
        threshold=float(raw.get("threshold", base.threshold)),
        cooldown_ms=int(raw.get("cooldown_ms", base.cooldown_ms)),
    )
```

with:

```python
def default_config() -> AppConfig:
    gestures = {
        name: GestureConfig(
            action=DEFAULT_ACTIONS[name],
            threshold=DEFAULT_THRESHOLDS[name],
            cooldown_ms=DEFAULT_COOLDOWN_MS[name],
            hold_ms=DEFAULT_HOLD_MS[name],
        )
        for name in GESTURE_NAMES
    }
    return AppConfig(calibration=CalibrationConfig(), gestures=gestures)


def _merge_gesture(name: str, raw: dict) -> GestureConfig:
    base = GestureConfig(
        action=DEFAULT_ACTIONS[name],
        threshold=DEFAULT_THRESHOLDS[name],
        cooldown_ms=DEFAULT_COOLDOWN_MS[name],
        hold_ms=DEFAULT_HOLD_MS[name],
    )
    action = raw.get("action", base.action)
    if action not in VALID_ACTIONS:
        action = base.action
    return GestureConfig(
        action=action,
        threshold=float(raw.get("threshold", base.threshold)),
        cooldown_ms=int(raw.get("cooldown_ms", base.cooldown_ms)),
        hold_ms=int(raw.get("hold_ms", base.hold_ms)),
    )
```

Then, in `load_config`, replace:

```python
    raw_gestures = raw.get("gestures", {})
    gestures = {
        name: _merge_gesture(name, raw_gestures.get(name, {}))
        for name in GESTURE_NAMES
    }
```

with:

```python
    raw_gestures = dict(raw.get("gestures", {}))
    for legacy_name, current_name in LEGACY_GESTURE_NAMES.items():
        if legacy_name in raw_gestures and current_name not in raw_gestures:
            raw_gestures[current_name] = raw_gestures[legacy_name]

    gestures = {
        name: _merge_gesture(name, raw_gestures.get(name, {}))
        for name in GESTURE_NAMES
    }
```

- [ ] **Step 6: Point the existing GUI at the new names**

This keeps the app runnable on the old UI until Task 5 replaces it.

In `src/facemesh_mouse/config_gui.py`, replace:

```python
_GESTURE_LABELS = {
    "blink_left": "Piscar olho A",
    "blink_right": "Piscar olho B",
    "blink_both": "Piscar os dois",
    "mouth_open": "Boca aberta",
    "eyebrow_raised": "Sobrancelha levantada",
}
```

with:

```python
_GESTURE_LABELS = {
    "blink_a": "Piscar olho A",
    "blink_b": "Piscar olho B",
    "blink_both": "Piscar os dois olhos",
    "eyebrow_a": "Sobrancelha A",
    "eyebrow_b": "Sobrancelha B",
    "eyebrow_both": "As duas sobrancelhas",
    "mouth_open": "Boca aberta",
    "mouth_left": "Boca fechada p/ esquerda",
    "mouth_right": "Boca fechada p/ direita",
}
```

Then replace:

```python
_METRIC_TO_GESTURE = {
    "ear_a": "blink_left",
    "ear_b": "blink_right",
    "mouth_open_ratio": "mouth_open",
    "eyebrow_raise_ratio": "eyebrow_raised",
}
```

with:

```python
_METRIC_TO_GESTURE = {
    "ear_a": "blink_a",
    "ear_b": "blink_b",
    "mouth_open_ratio": "mouth_open",
    "eyebrow_raise_ratio": "eyebrow_both",
}
```

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 55 tests

- [ ] **Step 8: Verify every module still compiles**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/*.py`
Expected: no output, exit code 0

- [ ] **Step 9: Commit**

```bash
git add src/facemesh_mouse/gestures.py src/facemesh_mouse/config.py src/facemesh_mouse/config_gui.py tests/
git commit -m "feat(gestures): nine gestures with per-gesture hold time and shared trigger progress"
```

---

### Task 3: `calibration_panel.py` — the Movimento tab

**Files:**
- Create: `src/facemesh_mouse/calibration_panel.py`
- Test: `tests/test_panels.py` (new file)

**Interfaces:**
- Consumes: `AppConfig` / `CalibrationConfig` fields `x_min`, `x_max`, `y_min`, `y_max`, `deadzone_px`, `sensitivity`; `FaceMetrics.nose_x`, `.nose_y`.
- Produces: `CalibrationPanel(parent, config: AppConfig)` with:
  - `.frame` — a `CTkFrame` the caller places (`pack`/`grid`)
  - `.update(metrics: FaceMetrics) -> None` — called per preview frame; tracks the running extreme while recording
  - `.cancel_capture() -> None` — discards an in-progress recording without writing it into the config

The panel never touches the camera or the engine: the shell feeds it metrics. A capture seeds its extreme from the first `update` after recording starts, so starting a capture needs no metrics argument.

This file is not wired into the app until Task 5 — it is complete and tested on its own first.

- [ ] **Step 1: Write the failing test**

Create `tests/test_panels.py`:

```python
import tkinter as tk

import pytest

ctk = pytest.importorskip("customtkinter")

from facemesh_mouse.calibration_panel import CalibrationPanel
from facemesh_mouse.config import default_config
from facemesh_mouse.tracker import FaceMetrics


def _metrics(nose_x=0.5, nose_y=0.5):
    return FaceMetrics(
        nose_x=nose_x,
        nose_y=nose_y,
        ear_a=0.3,
        ear_b=0.3,
        mouth_open_ratio=0.1,
        eyebrow_raise_a=0.05,
        eyebrow_raise_b=0.05,
        mouth_shift_ratio=0.0,
        landmarks=[],
    )


@pytest.fixture
def root():
    try:
        window = ctk.CTk()
    except tk.TclError as exc:  # no display available
        pytest.skip(f"Tk unavailable: {exc}")
    window.withdraw()
    yield window
    window.destroy()


def test_calibration_panel_builds_and_updates(root):
    config = default_config()
    panel = CalibrationPanel(root, config)
    panel.frame.pack()
    root.update()

    panel.update(_metrics())

    assert panel.frame.winfo_exists()


def test_capture_records_the_most_extreme_value_not_the_last(root):
    config = default_config()
    panel = CalibrationPanel(root, config)

    panel.start_capture("left")
    panel.update(_metrics(nose_x=0.40))
    panel.update(_metrics(nose_x=0.22))  # the true extreme
    panel.update(_metrics(nose_x=0.35))  # drifted back
    panel.stop_capture()

    assert config.calibration.x_min == pytest.approx(0.22)


def test_capture_down_records_the_maximum(root):
    config = default_config()
    panel = CalibrationPanel(root, config)

    panel.start_capture("down")
    panel.update(_metrics(nose_y=0.60))
    panel.update(_metrics(nose_y=0.81))
    panel.update(_metrics(nose_y=0.70))
    panel.stop_capture()

    assert config.calibration.y_max == pytest.approx(0.81)


def test_cancel_capture_discards_without_writing_to_config(root):
    config = default_config()
    before = config.calibration.x_min
    panel = CalibrationPanel(root, config)

    panel.start_capture("left")
    panel.update(_metrics(nose_x=0.05))
    panel.cancel_capture()

    assert config.calibration.x_min == before
    assert panel.recording_direction is None


def test_starting_a_capture_disables_the_other_buttons(root):
    panel = CalibrationPanel(root, default_config())

    panel.start_capture("left")
    assert str(panel.buttons["right"].cget("state")) == "disabled"

    panel.stop_capture()
    assert str(panel.buttons["right"].cget("state")) == "normal"


def test_sliders_write_into_the_config(root):
    config = default_config()
    panel = CalibrationPanel(root, config)

    panel.deadzone_var.set(9.0)
    panel.on_deadzone_change()
    panel.sensitivity_var.set(2.5)
    panel.on_sensitivity_change()

    assert config.calibration.deadzone_px == pytest.approx(9.0)
    assert config.calibration.sensitivity == pytest.approx(2.5)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_panels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.calibration_panel'`

- [ ] **Step 3: Create `calibration_panel.py`**

Create `src/facemesh_mouse/calibration_panel.py`:

```python
"""The "Movimento" tab: the four calibration capture toggles plus the
deadzone and sensitivity sliders.

The panel owns its recording state but never touches the camera -- the shell
feeds it one `FaceMetrics` per preview frame via `update`, and the running
extreme is seeded from the first frame after a capture starts.
"""
from __future__ import annotations

import customtkinter as ctk

from .config import AppConfig
from .tracker import FaceMetrics

CAPTURE_META = {
    "up": {
        "axis": "y",
        "extreme": "min",
        "label": "Cima",
        "guide": "Incline a cabeca o maximo para CIMA e clique em Parar.",
    },
    "down": {
        "axis": "y",
        "extreme": "max",
        "label": "Baixo",
        "guide": "Incline a cabeca o maximo para BAIXO e clique em Parar.",
    },
    "left": {
        "axis": "x",
        "extreme": "min",
        "label": "Esquerda",
        "guide": "Vire a cabeca o maximo para a ESQUERDA e clique em Parar.",
    },
    "right": {
        "axis": "x",
        "extreme": "max",
        "label": "Direita",
        "guide": "Vire a cabeca o maximo para a DIREITA e clique em Parar.",
    },
}

_HELP = (
    "Grave ate onde sua cabeca chega em cada direcao: clique em Gravar, mova "
    "a cabeca ate o limite confortavel e clique em Parar. O valor mais extremo "
    "durante a gravacao e o que fica salvo, entao nao precisa acertar o tempo "
    "do clique."
)


class CalibrationPanel:
    def __init__(self, parent, config: AppConfig) -> None:
        self._config = config
        self.recording_direction: str | None = None
        self.recording_extreme: float | None = None
        self.buttons: dict[str, ctk.CTkButton] = {}

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    # -- widgets -------------------------------------------------------
    def _build(self) -> None:
        self.frame.grid_columnconfigure(0, weight=1)
        row = 0

        ctk.CTkLabel(
            self.frame,
            text=_HELP,
            justify="left",
            wraplength=380,
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", pady=(4, 10))
        row += 1

        buttons = ctk.CTkFrame(self.frame, fg_color="transparent")
        buttons.grid(row=row, column=0, sticky="ew")
        buttons.grid_columnconfigure((0, 1), weight=1)
        for index, direction in enumerate(["up", "down", "left", "right"]):
            button = ctk.CTkButton(
                buttons,
                text=f"Gravar {CAPTURE_META[direction]['label']}",
                command=lambda d=direction: self.toggle_capture(d),
            )
            button.grid(row=index // 2, column=index % 2, padx=4, pady=4, sticky="ew")
            self.buttons[direction] = button
        row += 1

        self._guide_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            self.frame,
            textvariable=self._guide_var,
            justify="left",
            wraplength=380,
            anchor="w",
            text_color="#4da3ff",
        ).grid(row=row, column=0, sticky="ew", pady=(10, 0))
        row += 1

        self._live_var = ctk.StringVar(value="")
        ctk.CTkLabel(self.frame, textvariable=self._live_var, anchor="w").grid(
            row=row, column=0, sticky="ew"
        )
        row += 1

        self._status_var = ctk.StringVar(value=self._status_text())
        ctk.CTkLabel(
            self.frame, textvariable=self._status_var, anchor="w", text_color="gray70"
        ).grid(row=row, column=0, sticky="ew", pady=(6, 12))
        row += 1

        self.deadzone_var = ctk.DoubleVar(value=self._config.calibration.deadzone_px)
        self._deadzone_label = self._slider_row(
            row,
            "Zona morta (ignora tremores pequenos)",
            self.deadzone_var,
            0,
            15,
            self._deadzone_text(),
            lambda _value=None: self.on_deadzone_change(),
        )
        row += 2

        self.sensitivity_var = ctk.DoubleVar(value=self._config.calibration.sensitivity)
        self._sensitivity_label = self._slider_row(
            row,
            "Sensibilidade (velocidade do cursor)",
            self.sensitivity_var,
            0.3,
            3.0,
            self._sensitivity_text(),
            lambda _value=None: self.on_sensitivity_change(),
        )

    def _slider_row(self, row, title, variable, low, high, value_text, command):
        ctk.CTkLabel(self.frame, text=title, anchor="w").grid(
            row=row, column=0, sticky="ew"
        )
        holder = ctk.CTkFrame(self.frame, fg_color="transparent")
        holder.grid(row=row + 1, column=0, sticky="ew", pady=(0, 10))
        holder.grid_columnconfigure(0, weight=1)
        ctk.CTkSlider(
            holder, from_=low, to=high, variable=variable, command=command
        ).grid(row=0, column=0, sticky="ew")
        value_label = ctk.CTkLabel(holder, text=value_text, width=60)
        value_label.grid(row=0, column=1, padx=(8, 0))
        return value_label

    # -- text helpers ---------------------------------------------------
    def _status_text(self) -> str:
        cal = self._config.calibration
        return (
            f"Faixa gravada -- x: [{cal.x_min:.2f}, {cal.x_max:.2f}]   "
            f"y: [{cal.y_min:.2f}, {cal.y_max:.2f}]"
        )

    def _deadzone_text(self) -> str:
        return f"{self._config.calibration.deadzone_px:.0f} px"

    def _sensitivity_text(self) -> str:
        return f"{self._config.calibration.sensitivity:.1f}x"

    # -- slider callbacks -----------------------------------------------
    def on_deadzone_change(self) -> None:
        self._config.calibration.deadzone_px = round(self.deadzone_var.get(), 1)
        self._deadzone_label.configure(text=self._deadzone_text())

    def on_sensitivity_change(self) -> None:
        self._config.calibration.sensitivity = round(self.sensitivity_var.get(), 2)
        self._sensitivity_label.configure(text=self._sensitivity_text())

    # -- capture --------------------------------------------------------
    def toggle_capture(self, direction: str) -> None:
        if self.recording_direction == direction:
            self.stop_capture()
        else:
            self.start_capture(direction)

    def start_capture(self, direction: str) -> None:
        self.recording_direction = direction
        self.recording_extreme = None  # seeded by the next update()
        for name, button in self.buttons.items():
            if name == direction:
                button.configure(text="Parar")
            else:
                button.configure(state="disabled")
        self._guide_var.set(CAPTURE_META[direction]["guide"])
        self._live_var.set("Aguardando o rosto aparecer...")

    def stop_capture(self) -> None:
        """Commits the recorded extreme into the calibration and resets."""
        direction = self.recording_direction
        if direction is None:
            return
        if self.recording_extreme is not None:
            cal = self._config.calibration
            if direction == "up":
                cal.y_min = self.recording_extreme
            elif direction == "down":
                cal.y_max = self.recording_extreme
            elif direction == "left":
                cal.x_min = self.recording_extreme
            elif direction == "right":
                cal.x_max = self.recording_extreme
        self._reset_capture()
        self._status_var.set(self._status_text())

    def cancel_capture(self) -> None:
        """Drops an in-progress recording WITHOUT writing it into the config.
        The user never confirmed it, so discarding is the safe default."""
        if self.recording_direction is None:
            return
        self._reset_capture()

    def _reset_capture(self) -> None:
        self.recording_direction = None
        self.recording_extreme = None
        for name, button in self.buttons.items():
            button.configure(
                state="normal", text=f"Gravar {CAPTURE_META[name]['label']}"
            )
        self._guide_var.set("")
        self._live_var.set("")

    # -- per-frame ------------------------------------------------------
    def update(self, metrics: FaceMetrics) -> None:
        if self.recording_direction is None:
            return
        meta = CAPTURE_META[self.recording_direction]
        value = metrics.nose_y if meta["axis"] == "y" else metrics.nose_x
        if self.recording_extreme is None:
            self.recording_extreme = value
        elif meta["extreme"] == "min":
            self.recording_extreme = min(self.recording_extreme, value)
        else:
            self.recording_extreme = max(self.recording_extreme, value)
        self._live_var.set(f"Extremo capturado: {self.recording_extreme:.3f}")
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_panels.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 61 tests

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/calibration_panel.py tests/test_panels.py
git commit -m "feat(gui): CustomTkinter calibration panel with tested capture state machine"
```

---

### Task 4: `gesture_panel.py` — the Gestos tab

**Files:**
- Create: `src/facemesh_mouse/gesture_panel.py`
- Modify: `tests/test_panels.py`

**Interfaces:**
- Consumes: `config.GESTURE_NAMES`, `config.VALID_ACTIONS`, `GestureConfig.action/.threshold/.hold_ms` (Task 2); `gestures.trigger_progress` (Task 2).
- Produces: `GesturePanel(parent, config: AppConfig)` with:
  - `.frame` — a `CTkScrollableFrame` the caller places
  - `.update(metrics: FaceMetrics) -> None` — drives all nine live bars
  - `.apply_to_config() -> None` — writes the selected action and hold time of every row into the `AppConfig` it was given
  - `.GESTURE_LABELS` / `.ACTION_LABELS` module-level dicts (Portuguese display names)

Not wired into the app until Task 5.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_panels.py`:

```python
from facemesh_mouse.config import GESTURE_NAMES
from facemesh_mouse.gesture_panel import ACTION_LABELS, GESTURE_LABELS, GesturePanel


def test_gesture_panel_has_a_row_per_gesture(container):
    panel = GesturePanel(container, default_config())
    assert set(panel.rows) == set(GESTURE_NAMES)


def test_every_gesture_has_a_portuguese_label():
    assert set(GESTURE_LABELS) == set(GESTURE_NAMES)


def test_gesture_panel_updates_every_bar(container):
    panel = GesturePanel(container, default_config())
    panel.frame.pack()
    container.update()

    panel.update(_metrics())

    for name in GESTURE_NAMES:
        value = panel.rows[name].bar.get()
        assert 0.0 <= value <= 1.0


def test_blink_bar_fills_as_the_eye_closes(container):
    panel = GesturePanel(container, default_config())

    panel.update(_metrics())  # eyes open
    open_value = panel.rows["blink_a"].bar.get()

    closing = _metrics()
    closing.ear_a = 0.21  # exactly at the default threshold
    panel.update(closing)

    assert panel.rows["blink_a"].bar.get() > open_value


def test_apply_to_config_writes_action_and_hold_time(container):
    config = default_config()
    panel = GesturePanel(container, config)

    panel.rows["mouth_left"].action_var.set(ACTION_LABELS["scroll_up"])
    panel.rows["mouth_left"].hold_var.set(700)
    panel.apply_to_config()

    assert config.gestures["mouth_left"].action == "scroll_up"
    assert config.gestures["mouth_left"].hold_ms == 700


def test_panel_starts_from_the_configs_current_values(container):
    config = default_config()
    config.gestures["blink_a"].action = "scroll_down"
    config.gestures["blink_a"].hold_ms = 250

    panel = GesturePanel(container, config)

    assert panel.rows["blink_a"].action_var.get() == ACTION_LABELS["scroll_down"]
    assert panel.rows["blink_a"].hold_var.get() == 250
```

Note on fixtures: `tests/test_panels.py` shares **one** module-scoped Tk root
across every test in the file, and `container` hands each test its own child
frame inside it. Creating and destroying multiple Tk roots in a single
process fails intermittently under pytest's output capture once cv2 and
mediapipe are loaded, so no test in this file may construct its own root.
Take `container` as the parent, never `root`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_panels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.gesture_panel'`

- [ ] **Step 3: Create `gesture_panel.py`**

Create `src/facemesh_mouse/gesture_panel.py`:

```python
"""The "Gestos" tab: one row per gesture, each showing how close that gesture
is to firing, which mouse action it triggers, and how long it must be held.

The live bars are driven by `gestures.trigger_progress`, the same function
the detector's threshold logic is written against, so a bar can never
disagree with the gesture it describes about which direction means "closer
to firing".
"""
from __future__ import annotations

from dataclasses import dataclass

import customtkinter as ctk

from . import config as config_mod
from .config import AppConfig
from .gestures import trigger_progress
from .tracker import FaceMetrics

GESTURE_LABELS = {
    "blink_a": "Piscar olho A",
    "blink_b": "Piscar olho B",
    "blink_both": "Piscar os dois olhos",
    "eyebrow_a": "Sobrancelha A",
    "eyebrow_b": "Sobrancelha B",
    "eyebrow_both": "As duas sobrancelhas",
    "mouth_open": "Boca aberta",
    "mouth_left": "Boca fechada p/ esquerda",
    "mouth_right": "Boca fechada p/ direita",
}

ACTION_LABELS = {
    "none": "(nenhuma)",
    "left_click": "Clique esquerdo",
    "right_click": "Clique direito",
    "double_click": "Duplo clique",
    "scroll_up": "Scroll cima",
    "scroll_down": "Scroll baixo",
}
ACTION_BY_LABEL = {label: action for action, label in ACTION_LABELS.items()}

_HELP = (
    "A barra enche conforme voce se aproxima de disparar o gesto. Os rotulos "
    "A e B dos olhos e das sobrancelhas sao internos: faca o gesto e veja qual "
    "barra reage. O tempo e quanto voce precisa segurar a expressao para ela "
    "valer -- e o que impede piscadas naturais de virarem cliques."
)


@dataclass
class GestureRow:
    bar: ctk.CTkProgressBar
    action_var: ctk.StringVar
    hold_var: ctk.IntVar


class GesturePanel:
    def __init__(self, parent, config: AppConfig) -> None:
        self._config = config
        self.rows: dict[str, GestureRow] = {}

        self.frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._build()

    def _build(self) -> None:
        self.frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.frame,
            text=_HELP,
            justify="left",
            wraplength=380,
            anchor="w",
            text_color="gray70",
        ).grid(row=0, column=0, sticky="ew", pady=(4, 10))

        for index, name in enumerate(config_mod.GESTURE_NAMES, start=1):
            self.rows[name] = self._build_row(index, name)

    def _build_row(self, row: int, name: str) -> GestureRow:
        gesture_cfg = self._config.gestures[name]

        holder = ctk.CTkFrame(self.frame)
        holder.grid(row=row, column=0, sticky="ew", pady=4)
        holder.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            holder, text=GESTURE_LABELS[name], anchor="w", font=("Segoe UI", 13, "bold")
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))

        bar = ctk.CTkProgressBar(holder, height=10)
        bar.set(0.0)
        bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        controls = ctk.CTkFrame(holder, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        controls.grid_columnconfigure(1, weight=1)

        action_var = ctk.StringVar(value=ACTION_LABELS[gesture_cfg.action])
        ctk.CTkOptionMenu(
            controls,
            variable=action_var,
            values=list(ACTION_LABELS.values()),
            width=150,
        ).grid(row=0, column=0, sticky="w")

        hold_var = ctk.IntVar(value=gesture_cfg.hold_ms)
        hold_label = ctk.CTkLabel(controls, text=f"{gesture_cfg.hold_ms} ms", width=64)

        def on_hold(value, label=hold_label, var=hold_var) -> None:
            var.set(int(float(value)))
            label.configure(text=f"{var.get()} ms")

        hold_slider = ctk.CTkSlider(
            controls, from_=0, to=1000, number_of_steps=20, command=on_hold
        )
        hold_slider.set(gesture_cfg.hold_ms)  # start at the saved value
        hold_slider.grid(row=0, column=1, sticky="ew", padx=8)
        hold_label.grid(row=0, column=2, sticky="e")

        return GestureRow(bar=bar, action_var=action_var, hold_var=hold_var)

    def update(self, metrics: FaceMetrics) -> None:
        for name, row in self.rows.items():
            threshold = self._config.gestures[name].threshold
            row.bar.set(trigger_progress(name, metrics, threshold))

    def apply_to_config(self) -> None:
        for name, row in self.rows.items():
            gesture_cfg = self._config.gestures[name]
            gesture_cfg.action = ACTION_BY_LABEL[row.action_var.get()]
            gesture_cfg.hold_ms = int(row.hold_var.get())
```

Note: delete the stray `ctk.CTkSlider  # (kept on one line above; no further slider needed)` line — it is a no-op expression that must not ship. The slider above it is the only one the row needs, and its initial position must be set right after creation so it reflects the saved `hold_ms`; assign it to a local and call `.set(gesture_cfg.hold_ms)`:

```python
        hold_slider = ctk.CTkSlider(
            controls, from_=0, to=1000, number_of_steps=20, command=on_hold
        )
        hold_slider.set(gesture_cfg.hold_ms)
        hold_slider.grid(row=0, column=1, sticky="ew", padx=8)
        hold_label.grid(row=0, column=2, sticky="e")
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_panels.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 67 tests

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/gesture_panel.py tests/test_panels.py
git commit -m "feat(gui): CustomTkinter gesture panel driven by shared trigger_progress"
```

---

### Task 5: Shell rewrite, wiring, packaging, docs

**Files:**
- Rewrite: `src/facemesh_mouse/config_gui.py`
- Modify: `src/facemesh_mouse/main.py`
- Modify: `requirements.txt`
- Modify: `README.md`
- Modify: `tests/test_panels.py`

**Interfaces:**
- Consumes: `CalibrationPanel` (Task 3), `GesturePanel` (Task 4).
- Produces: `config_gui.create_root() -> ctk.CTk` (sets appearance mode and returns the app root, so `main.py` needs no CustomTkinter import), and the same `ConfigWindow(root, engine, config, config_path, on_start)` / `.show()` interface `main.py` already uses.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_panels.py`:

First, change the module-scoped `root` fixture in `tests/test_panels.py` so
the shared root is built by `create_root()` itself. The fixture then doubles
as the coverage for it, and no second Tk root is ever created — which
matters, because a second root in the same process is exactly the operation
that fails intermittently under pytest's output capture:

```python
@pytest.fixture(scope="module")
def root():
    from facemesh_mouse.config_gui import create_root

    try:
        window = create_root()
    except tk.TclError as exc:  # no display available
        pytest.skip(f"Tk unavailable: {exc}")
    window.withdraw()
    yield window
    window.destroy()
```

Then add this test, which asserts on that shared root rather than building
its own:

```python
def test_create_root_returns_a_usable_tk_root(root):
    assert isinstance(root, tk.Tk)

    root.deiconify()
    root.update()
    assert root.winfo_viewable()

    root.withdraw()
    root.update()
    assert not root.winfo_viewable()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_panels.py -v`
Expected: FAIL with `ImportError: cannot import name 'create_root' from 'facemesh_mouse.config_gui'`

- [ ] **Step 3: Replace `config_gui.py` in full**

Replace the entire contents of `src/facemesh_mouse/config_gui.py` with:

```python
"""Config window shell: live preview on the left, tabbed settings on the
right. Reads the engine's SharedState for preview only -- it never touches
the camera directly (see engine.py).

`ctk.CTk` subclasses `tk.Tk`, so the tray thread, the global hotkeys, the
single-instance listener, and the skip-wizard startup path keep using
`root.after` / `withdraw` / `deiconify` exactly as before.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from . import config as config_mod
from .calibration_panel import CalibrationPanel
from .config import AppConfig
from .engine import Engine
from .gesture_panel import GesturePanel

PREVIEW_SIZE = (480, 360)

_HELP_TEXT = (
    "Como usar\n\n"
    "1. Movimento -- grave ate onde sua cabeca chega em cada direcao. O cursor "
    "anda de forma relativa, como um mouse de verdade.\n\n"
    "2. Gestos -- veja qual barra reage a cada expressao e escolha o que ela "
    "faz. O tempo de cada gesto e quanto voce precisa segurar a expressao: e o "
    "que impede piscadas naturais de virarem cliques. Deixe em 0 ms so se "
    "quiser disparo imediato.\n\n"
    "3. Iniciar -- a janela some e o cursor passa a seguir a cabeca.\n\n"
    "Atalhos\n\n"
    "Ctrl+Alt+P pausa e retoma. Use como quem levanta o mouse da mesa: o "
    "cursor congela, voce reposiciona a cabeca numa posicao confortavel, e ao "
    "retomar o controle continua exatamente de onde parou, sem pular.\n\n"
    "Ctrl+Alt+O reabre esta janela. Clicar no icone da bandeja tambem reabre; "
    "o botao direito no icone mostra o menu completo.\n\n"
    "Abrir o app de novo enquanto ele ja esta rodando nao cria uma segunda "
    "copia: reabre esta janela."
)


def create_root() -> ctk.CTk:
    """Creates the single Tk root the whole app runs on."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    return ctk.CTk()


class ConfigWindow:
    def __init__(
        self,
        root: ctk.CTk,
        engine: Engine,
        config: AppConfig,
        config_path: str,
        on_start: Callable[[AppConfig], None],
    ) -> None:
        self._root = root
        self._engine = engine
        self._config = config
        self._config_path = config_path
        self._on_start = on_start
        self._tk_image = None
        self._after_id = None

        root.title("FaceMesh Mouse")
        root.protocol("WM_DELETE_WINDOW", self._start_and_hide)

        self._build_widgets()
        self._tick()

    # -- widgets --------------------------------------------------------
    def _build_widgets(self) -> None:
        self._root.grid_columnconfigure(1, weight=1)
        self._root.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self._root)
        left.grid(row=0, column=0, padx=12, pady=12, sticky="n")

        self._preview = tk.Label(left, background="#1f1f1f")
        self._preview.pack(padx=10, pady=10)

        ctk.CTkButton(
            left,
            text="Iniciar controle do mouse",
            height=44,
            font=("Segoe UI", 14, "bold"),
            command=self._start_and_hide,
        ).pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            left,
            text="A janela some e o controle segue em segundo plano.",
            text_color="gray70",
        ).pack(padx=10, pady=(0, 10))

        tabs = ctk.CTkTabview(self._root, width=430)
        tabs.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="nsew")
        tabs.add("Movimento")
        tabs.add("Gestos")
        tabs.add("Ajuda")

        self._calibration = CalibrationPanel(tabs.tab("Movimento"), self._config)
        self._calibration.frame.pack(fill="both", expand=True)

        self._gestures = GesturePanel(tabs.tab("Gestos"), self._config)
        self._gestures.frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            tabs.tab("Ajuda"),
            text=_HELP_TEXT,
            justify="left",
            wraplength=390,
            anchor="nw",
        ).pack(fill="both", expand=True, padx=6, pady=6)

    # -- live preview loop ----------------------------------------------
    def _tick(self) -> None:
        # Skipped entirely while hidden: with the app now starting straight
        # into background tracking, "hidden" is the normal state for a whole
        # session, and this loop would otherwise decode and convert a frame
        # 30 times a second for a window nobody can see.
        if self._root.winfo_viewable():
            frame, metrics = self._engine.state.snapshot()
            if frame is not None:
                self._render_preview(frame, metrics)
            if metrics is not None:
                self._calibration.update(metrics)
                self._gestures.update(metrics)

        self._after_id = self._root.after(33, self._tick)

    def _render_preview(self, frame, metrics) -> None:
        display = cv2.resize(frame, PREVIEW_SIZE)
        if metrics is not None:
            height, width = display.shape[:2]
            center = (int(metrics.nose_x * width), int(metrics.nose_y * height))
            cv2.circle(display, center, 5, (0, 0, 255), -1)
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        self._tk_image = ImageTk.PhotoImage(image=Image.fromarray(rgb))
        self._preview.configure(image=self._tk_image)

    # -- lifecycle -------------------------------------------------------
    def _start_and_hide(self) -> None:
        self._calibration.cancel_capture()
        self._gestures.apply_to_config()
        config_mod.save_config(self._config_path, self._config)
        self._on_start(self._config)
        self._root.withdraw()

    def show(self) -> None:
        self._root.deiconify()
        self._root.lift()
```

- [ ] **Step 4: Point `main.py` at `create_root`**

In `src/facemesh_mouse/main.py`, replace:

```python
from .config_gui import ConfigWindow
```

with:

```python
from .config_gui import ConfigWindow, create_root
```

and replace:

```python
    root = tk.Tk()
    screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
```

with:

```python
    root = create_root()
    screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
```

Leave the camera-failure path's `tk.Tk()` alone — it only anchors a
`messagebox` before `sys.exit(1)`, so the `import tkinter as tk` line stays.

- [ ] **Step 5: Add the dependency**

In `requirements.txt`, add a line:

```
customtkinter==6.0.0
```

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 68 tests

- [ ] **Step 7: Compile-check every module**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/*.py`
Expected: no output, exit code 0

- [ ] **Step 8: Update the README**

In `README.md`, replace the intro paragraph:

```markdown
Controle o mouse com a cabeça: a ponta do nariz move o cursor, e gestos
faciais (piscar, boca aberta, sobrancelha levantada) disparam clique
esquerdo/direito/duplo ou scroll — tudo configurável numa janela de
calibração. Depois de configurar, o tracking continua rodando em segundo
plano (sem janela visível), com ícone na bandeja e atalhos globais.
```

with:

```markdown
Controle o mouse com a cabeça: a ponta do nariz move o cursor, e nove gestos
faciais (piscar cada olho ou os dois, levantar cada sobrancelha ou as duas,
abrir a boca, mover a boca fechada para cada lado) disparam clique
esquerdo/direito/duplo ou scroll — tudo configurável numa janela de
calibração. Cada gesto tem um tempo de espera: você precisa segurar a
expressão por alguns décimos de segundo para ela valer, o que impede que
piscadas naturais virem cliques. Depois de configurar, o tracking continua
rodando em segundo plano (sem janela visível), com ícone na bandeja e
atalhos globais.
```

Then replace the numbered "Rodar" steps 2 and 3:

```markdown
2. **Mapear gestos**: observe as barras `Olho A` / `Olho B` / `Boca aberta`
   / `Sobrancelha levantada` reagirem enquanto faz cada gesto, pra saber
   qual reage a qual olho (os nomes "A"/"B" são só internos, sem relação
   fixa com esquerda/direita anatômica por causa do espelhamento da
   câmera), e escolha uma ação de mouse pra cada gesto no dropdown.
```

with:

```markdown
2. **Mapear gestos**: nove gestos, cada um com uma barra que enche conforme
   você se aproxima de dispará-lo. Faça a expressão e veja qual barra reage
   pra saber qual é qual (os nomes "A"/"B" de olho e sobrancelha são só
   internos, sem relação fixa com esquerda/direita anatômica por causa do
   espelhamento da câmera; já a boca para os lados segue o que você vê no
   preview). Escolha a ação de mouse de cada gesto e, no slider ao lado,
   por quanto tempo a expressão precisa ser segurada pra valer (padrão
   400ms — bem acima de uma piscada natural, que dura ~100-150ms).
```

Then, in the "Build do executável (.exe)" section, replace the build command:

```powershell
.venv\Scripts\pyinstaller --onefile --windowed --paths src --collect-data mediapipe --collect-all cv2 -n facemesh-mouse run.py
```

with:

```powershell
.venv\Scripts\pyinstaller --onefile --windowed --paths src --collect-data mediapipe --collect-all cv2 --collect-data customtkinter -n facemesh-mouse run.py
```

and add below the existing `--paths src` explanation paragraph:

```markdown
`--collect-data customtkinter` também é obrigatório: o CustomTkinter carrega
temas em JSON e fontes em tempo de execução, e a análise estática do
PyInstaller não enxerga esses arquivos — sem a flag o exe abre e quebra ao
montar a janela.
```

- [ ] **Step 9: Manual verification checklist**

Run `.venv\Scripts\python run.py` with a real webcam. If `config.json` exists, the window won't appear — delete or rename it first to reach the wizard, or press `Ctrl+Alt+O` after launch.

1. The window opens dark-themed, with the webcam preview and a big "Iniciar controle do mouse" button on the left and three tabs (Movimento / Gestos / Ajuda) on the right.
2. **Movimento tab:** clicking "Gravar Cima" relabels that button to "Parar", disables the other three, and shows a blue guide line plus a live "Extremo capturado" readout that tracks your head. Clicking "Parar" commits it and updates the "Faixa gravada" line. Both sliders move and their px/x labels follow.
3. **Gestos tab:** all nine rows are present and scroll. Blink one eye — exactly one of "Piscar olho A"/"Piscar olho B" fills. Raise one eyebrow — one eyebrow bar fills. Push your closed mouth left, then right — the two lateral bars respond independently and in the direction you see in the mirrored preview.
4. **Blink safety (the point of this change):** with the default 400ms hold and "Piscar olho A" mapped to left click, start tracking and blink normally several times — no clicks fire. Then deliberately close that one eye and hold it — one click fires, and holding longer does not repeat it.
5. **Ajuda tab** renders the help text.
6. Click "Iniciar controle do mouse" — the window hides and the cursor follows your head.
7. Press `Ctrl+Alt+O` — the window comes back with your settings intact. Confirm `config.json` now contains the nine gestures with `hold_ms` on each.
8. **Legacy migration:** with the app closed, confirm your pre-existing `config.json`'s mappings survived (a file that had `eyebrow_raised` should now drive `eyebrow_both`).

- [ ] **Step 10: Commit**

```bash
git add src/facemesh_mouse/config_gui.py src/facemesh_mouse/main.py requirements.txt README.md tests/test_panels.py
git commit -m "feat(gui): rebuild config window on CustomTkinter with tabbed layout"
```

---

## Self-Review Notes

- **Spec coverage:** eyebrow split → Task 1; yaw-tolerant lateral mouth metric → Task 1; nine-gesture roster → Task 2; hold time → Task 2; `trigger_progress` → Task 2; config schema + legacy migration → Task 2; CustomTkinter rebuild → Tasks 3-5; file split into shell + two panels → Tasks 3-5; preview-loop `winfo_viewable` gating → Task 5; `create_root` keeping CustomTkinter out of `main.py` → Task 5; packaging flag + README → Task 5; every test named in the spec's Testing section → Tasks 1-5.
- **Placeholder scan:** no TBD/TODO; every step carries literal code or an exact command.
- **Type/name consistency checked:** `signed_lateral_offset`'s signature matches between its Task 1 definition, its Task 1 use in `process`, and its tests. `trigger_progress(name, metrics, threshold)` matches between the Task 2 definition, the Task 4 panel call, and both tasks' tests. `FaceMetrics`'s three new field names are identical across `tracker.py`, all four test helpers, `gestures.py`, and both panels. `CalibrationPanel`/`GesturePanel`'s `.frame`, `.update`, `.cancel_capture`, `.apply_to_config`, and `.rows` match between their defining tasks, their tests, and the Task 5 shell.
- **App runnable after every task:** Task 1 keeps the five old gestures via a transitional average; Task 2 updates the old GUI's two label maps so it runs with nine; Tasks 3-4 add files that nothing imports yet; Task 5 swaps the shell over.
- **Out of scope, confirmed absent from every task:** extra expressions beyond the nine, GUI threshold editing, a hold-progress countdown, a light/dark toggle, and any change to `engine.py`, `mouse_controller.py`, `tray.py`, `hotkeys.py`, or `single_instance.py`.
