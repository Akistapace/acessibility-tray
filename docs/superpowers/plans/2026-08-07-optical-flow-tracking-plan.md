# Optical-Flow Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-landmark cursor mapping with a many-points pipeline — points tracked by Lucas-Kanade optical flow and averaged, a power-curve acceleration in place of the EMA, and per-axis sensitivity replacing the four-point calibration.

**Architecture:** A new `point_tracker.py` owns the optical-flow point set (seed from landmarks, track, prune, average). `mouse_controller.py` drops the calibration-derived scale and the EMA for `accelerate()` plus per-axis sensitivity. `engine.py` feeds the grayscale frame to the tracker and hands the averaged movement to the controller. The Movimento tab becomes four sliders.

**Tech Stack:** Python 3.11, OpenCV (`cv2.calcOpticalFlowPyrLK`), MediaPipe, CustomTkinter, pytest.

## Global Constraints

- Distance thresholds in `point_tracker.py` scale with head size (a fraction of it) rather than fixed pixel counts, so behavior stays consistent regardless of how close the user sits to the camera.
- Every module keeps `from __future__ import annotations` as its first import.
- UI strings stay in Portuguese **with correct diacritics** (`ç`, `ã`, `á`, `é`, `í`, `ó`, `ú`, and the verb `é`). A previous pass shipped them stripped and it had to be fixed — do not regress.
- Run tests with `.venv\Scripts\python -m pytest tests/ -v` from the repo root. The suite must end with **0 skipped**.
- `tests/test_panels.py` has a module-scoped `root` fixture and a function-scoped `container` fixture. Never construct another Tk root — more than one per process fails intermittently under pytest's output capture.
- **Pruning order is load-bearing**: status filter → grid de-duplication → region cull, and all of it before movement is read. OpenCV reports `status == 1` for points that have visibly diverged; the region cull is the only thing that catches them.
- Do not modify `gestures.py`, `tray.py`, `hotkeys.py`, `single_instance.py`, or `gesture_panel.py`.
- Nine gestures, `hold_ms`, and the gesture-name migration from the previous plan stay exactly as they are.

---

### Task 1: `point_tracker.py` — optical-flow point set

**Files:**
- Create: `src/facemesh_mouse/point_tracker.py`
- Test: `tests/test_point_tracker.py` (new)

**Interfaces:**
- Produces:
  - `PRUNING_GRID: float = 5.0`, `MIN_DISTANCE_TO_ADD: float = 7.5`, `REGION_X_STRETCH: float = 1.4`
  - `prune_points(points, prev_points, status, nose, head_size) -> tuple[np.ndarray, np.ndarray]` — pure; applies the three prune stages in order and returns the surviving `(current, previous)` arrays.
  - `should_add_point(candidate, points) -> bool` — pure; the `maybeAddPoint` rule.
  - `mean_movement(points, prev_points) -> tuple[float, float]` — pure.
  - `PointTracker` with `.update(gray, nose, head_size, candidates) -> None`, `.get_movement() -> tuple[float, float]`, `.reset() -> None`, `.point_count -> int`.
- Consumes: nothing from other tasks. Nothing imports this file until Task 2.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_point_tracker.py`:

```python
import cv2
import numpy as np
import pytest

from facemesh_mouse.point_tracker import (
    MIN_DISTANCE_TO_ADD,
    PointTracker,
    mean_movement,
    prune_points,
    should_add_point,
)


def _pts(*pairs):
    return np.array(pairs, dtype=np.float32).reshape(-1, 2)


def test_prune_drops_points_optical_flow_lost():
    cur = _pts((10, 10), (20, 20))
    prev = _pts((9, 10), (19, 20))
    status = np.array([1, 0], dtype=np.uint8)

    kept_cur, kept_prev = prune_points(cur, prev, status, nose=(15, 15), head_size=100)

    assert len(kept_cur) == 1
    assert kept_cur[0].tolist() == [10, 10]
    assert kept_prev[0].tolist() == [9, 10]


def test_prune_deduplicates_points_sharing_a_grid_cell():
    # (10,10) and (12,12) both fall in grid cell (2,2) at a 5px grid
    cur = _pts((10, 10), (12, 12), (40, 40))
    prev = _pts((10, 10), (12, 12), (40, 40))
    status = np.array([1, 1, 1], dtype=np.uint8)

    kept_cur, _ = prune_points(cur, prev, status, nose=(20, 20), head_size=100)

    assert len(kept_cur) == 2


def test_prune_culls_points_beyond_the_head_ellipse():
    nose = (100.0, 100.0)
    cur = _pts((110, 100), (400, 100))  # one near, one far away
    prev = cur.copy()
    status = np.array([1, 1], dtype=np.uint8)

    kept_cur, _ = prune_points(cur, prev, status, nose=nose, head_size=60)

    assert len(kept_cur) == 1
    assert kept_cur[0].tolist() == [110, 100]


def test_region_cull_is_stretched_horizontally():
    """The cull ellipse is 1.4x wider than tall, so the same distance
    survives vertically but not horizontally."""
    nose = (100.0, 100.0)
    head_size = 60.0
    offset = 50.0  # 50 * 1.4 = 70 > 60 horizontally, but 50 < 60 vertically

    horizontal = prune_points(
        _pts((100 + offset, 100)), _pts((100 + offset, 100)),
        np.array([1], dtype=np.uint8), nose, head_size,
    )[0]
    vertical = prune_points(
        _pts((100, 100 + offset)), _pts((100, 100 + offset)),
        np.array([1], dtype=np.uint8), nose, head_size,
    )[0]

    assert len(horizontal) == 0
    assert len(vertical) == 1


def test_should_add_point_rejects_a_candidate_near_an_existing_one():
    existing = _pts((100, 100))
    too_close = (100 + MIN_DISTANCE_TO_ADD - 1, 100 + MIN_DISTANCE_TO_ADD - 1)

    assert not should_add_point(too_close, existing)


def test_should_add_point_accepts_a_candidate_clear_on_both_axes():
    existing = _pts((100, 100))
    far = (100 + MIN_DISTANCE_TO_ADD + 1, 100 + MIN_DISTANCE_TO_ADD + 1)

    assert should_add_point(far, existing)


def test_should_add_point_accepts_anything_when_there_are_no_points():
    assert should_add_point((5, 5), _pts())


def test_mean_movement_averages_every_point():
    cur = _pts((10, 10), (20, 30))
    prev = _pts((8, 9), (18, 26))

    dx, dy = mean_movement(cur, prev)

    assert dx == pytest.approx(2.0)
    assert dy == pytest.approx(2.5)


def test_mean_movement_is_zero_without_points():
    assert mean_movement(_pts(), _pts()) == (0.0, 0.0)


def _textured_frame(seed=0):
    rng = np.random.default_rng(seed)
    frame = rng.integers(0, 255, (240, 320), dtype=np.uint8)
    return cv2.GaussianBlur(frame, (5, 5), 0)


def test_tracker_recovers_a_known_translation_through_real_optical_flow():
    """Pins the cv2.calcOpticalFlowPyrLK call's argument order and return
    shapes against a synthetic frame shifted by a known amount."""
    first = _textured_frame()
    shift_x, shift_y = 6, -3
    second = cv2.warpAffine(
        first, np.float32([[1, 0, shift_x], [0, 1, shift_y]]), (320, 240)
    )

    tracker = PointTracker()
    nose = (160.0, 120.0)
    candidates = [(150.0, 110.0), (170.0, 130.0), (160.0, 100.0)]

    tracker.update(first, nose, head_size=120.0, candidates=candidates)
    assert tracker.point_count == 3
    assert tracker.get_movement() == (0.0, 0.0)  # nothing to compare against yet

    tracker.update(second, nose, head_size=120.0, candidates=candidates)
    dx, dy = tracker.get_movement()

    assert dx == pytest.approx(shift_x, abs=1.0)
    assert dy == pytest.approx(shift_y, abs=1.0)


def test_reset_drops_every_point_and_zeroes_movement():
    tracker = PointTracker()
    tracker.update(_textured_frame(), (160.0, 120.0), 120.0, [(150.0, 110.0)])
    assert tracker.point_count == 1

    tracker.reset()

    assert tracker.point_count == 0
    assert tracker.get_movement() == (0.0, 0.0)


def test_candidates_are_not_re_added_once_tracked():
    tracker = PointTracker()
    frame = _textured_frame()
    candidates = [(150.0, 110.0), (170.0, 130.0)]

    tracker.update(frame, (160.0, 120.0), 120.0, candidates)
    tracker.update(frame, (160.0, 120.0), 120.0, candidates)

    assert tracker.point_count == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_point_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.point_tracker'`

- [ ] **Step 3: Create `point_tracker.py`**

```python
"""Optical-flow point tracking for cursor movement.

Tracks several points on rigid parts of the face with Lucas-Kanade optical
flow, using OpenCV.

Averaging the frame-to-frame movement of several tracked points cancels
noise that a single face landmark carries straight through to the cursor.
"""
from __future__ import annotations

import cv2
import numpy as np

# Points closer together than one grid cell are collapsed: points that have
# converged carry no extra information, and a cluster would weight one part
# of the face more than the rest.
PRUNING_GRID = 5.0

# A candidate is skipped if an existing point is already within this
# distance on either axis. Established points already carry motion history,
# so they are preferred over fresh ones.
MIN_DISTANCE_TO_ADD = PRUNING_GRID * 1.5

# The cull region is an ellipse wider than it is tall, matching a face.
REGION_X_STRETCH = 1.4

_LK_PARAMS = dict(
    winSize=(20, 20),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
)


def _empty() -> np.ndarray:
    return np.empty((0, 2), dtype=np.float32)


def prune_points(points, prev_points, status, nose, head_size):
    """Drops points optical flow lost, collapses near-duplicates, and culls
    points that have drifted off the face -- in that order.

    Optical flow reports success for points that have visibly diverged, so
    the region cull rather than `status` is what keeps a runaway point from
    dragging the average. Returns the surviving (current, previous) arrays.
    """
    keep = np.asarray(status).reshape(-1) == 1
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)[keep]
    prev_points = np.asarray(prev_points, dtype=np.float32).reshape(-1, 2)[keep]

    seen_cells = {}
    for index, (x, y) in enumerate(points):
        seen_cells[(int(x // PRUNING_GRID), int(y // PRUNING_GRID))] = index
    if seen_cells:
        unique = sorted(seen_cells.values())
        points = points[unique]
        prev_points = prev_points[unique]

    if len(points):
        nose_x, nose_y = nose
        distances = np.hypot(
            (points[:, 0] - nose_x) * REGION_X_STRETCH, points[:, 1] - nose_y
        )
        inside = distances <= head_size
        points = points[inside]
        prev_points = prev_points[inside]

    return points, prev_points


def should_add_point(candidate, points) -> bool:
    """Whether a candidate is far enough from every tracked point to be
    worth adding, comparing each axis separately (the grid pruning makes
    Euclidean distance pointless here)."""
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    if not len(points):
        return True
    close_x = np.abs(points[:, 0] - candidate[0]) <= MIN_DISTANCE_TO_ADD
    close_y = np.abs(points[:, 1] - candidate[1]) <= MIN_DISTANCE_TO_ADD
    return not bool(np.any(close_x | close_y))


def mean_movement(points, prev_points) -> tuple[float, float]:
    """Average frame-to-frame movement across every tracked point, in
    camera pixels."""
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    prev_points = np.asarray(prev_points, dtype=np.float32).reshape(-1, 2)
    if not len(points):
        return 0.0, 0.0
    delta = points - prev_points
    return float(delta[:, 0].mean()), float(delta[:, 1].mean())


class PointTracker:
    """Tracks a small set of face points across frames via optical flow."""

    def __init__(self) -> None:
        self._prev_gray = None
        self._points = _empty()
        self._prev_points = _empty()

    @property
    def point_count(self) -> int:
        return len(self._points)

    def reset(self) -> None:
        """Drops every point and the previous frame, so the next update
        starts fresh. Used when control resumes or the face is lost."""
        self._prev_gray = None
        self._points = _empty()
        self._prev_points = _empty()

    def update(self, gray, nose, head_size, candidates) -> None:
        if self._prev_gray is not None and len(self._points):
            tracked, status, _err = cv2.calcOpticalFlowPyrLK(
                self._prev_gray, gray,
                self._points.reshape(-1, 1, 2), None,
                **_LK_PARAMS,
            )
            self._points, self._prev_points = prune_points(
                tracked.reshape(-1, 2), self._points, status, nose, head_size
            )
        else:
            self._prev_points = self._points.copy()

        for candidate in candidates:
            if should_add_point(candidate, self._points):
                self._points = np.vstack(
                    [self._points, np.array([candidate], dtype=np.float32)]
                )
                self._prev_points = np.vstack(
                    [self._prev_points, np.array([candidate], dtype=np.float32)]
                )

        self._prev_gray = gray

    def get_movement(self) -> tuple[float, float]:
        return mean_movement(self._points, self._prev_points)
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_point_tracker.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/point_tracker.py tests/test_point_tracker.py
git commit -m "feat(tracking): optical-flow point tracker"
```

---

### Task 2: Swap the cursor path over to optical flow

**Files:**
- Modify: `src/facemesh_mouse/config.py` (`CalibrationConfig` + `load_config`)
- Modify: `src/facemesh_mouse/mouse_controller.py`
- Modify: `src/facemesh_mouse/engine.py`
- Modify: `src/facemesh_mouse/calibration_panel.py` (field references only — the tab rebuild is Task 3)
- Test: `tests/test_mouse_controller.py`, `tests/test_config.py`, `tests/test_engine.py`

This task is atomic: the config fields, the controller math, and the engine wiring all reference each other, so splitting it would leave the app unable to start.

**Interfaces:**
- Consumes: `PointTracker`, from Task 1.
- Produces:
  - `CalibrationConfig(sensitivity_x=0.025, sensitivity_y=0.05, acceleration=0.5, motion_threshold_px=0.0)` — the four previous fields are gone.
  - `mouse_controller.accelerate(delta: float, acceleration: float) -> float`
  - `MouseController.move_cursor(movement_x: float, movement_y: float) -> None` — **signature changed**: it now takes averaged camera-pixel movement, not `FaceMetrics`.
  - `MouseController.reanchor() -> None` — **no longer takes metrics**.

- [ ] **Step 1: Write the failing config tests**

In `tests/test_config.py`, replace the three tests named
`test_default_config_has_deadzone_and_sensitivity_defaults`,
`test_load_config_partial_file_merges_deadzone_and_sensitivity_with_defaults`, and
`test_save_then_load_round_trip_includes_deadzone_and_sensitivity` with:

```python
def test_default_config_has_the_tracking_defaults():
    cal = config_mod.default_config().calibration
    assert cal.sensitivity_x == 0.025
    assert cal.sensitivity_y == 0.05
    assert cal.acceleration == 0.5
    assert cal.motion_threshold_px == 0.0


def test_tracking_fields_round_trip(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.calibration.sensitivity_x = 0.04
    original.calibration.acceleration = 0.8

    config_mod.save_config(path, original)
    loaded = config_mod.load_config(path)

    assert loaded.calibration.sensitivity_x == 0.04
    assert loaded.calibration.acceleration == 0.8


def test_legacy_calibration_keys_are_ignored_and_gestures_survive(tmp_path):
    """A config from before the optical-flow switch has four-point bounds
    that have no sensitivity equivalent. They are dropped; the defaults
    apply; the user's gesture mappings must still migrate."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "calibration": {"x_min": 0.4, "x_max": 0.6, "smoothing": 0.7, "deadzone_px": 15.0},
                "gestures": {"blink_left": {"action": "scroll_up"}},
            }
        )
    )

    loaded = config_mod.load_config(path)

    assert loaded.calibration.sensitivity_x == 0.025
    assert loaded.calibration.motion_threshold_px == 0.0
    assert not hasattr(loaded.calibration, "x_min")
    assert loaded.gestures["blink_a"].action == "scroll_up"
```

Also update `test_save_then_load_round_trip`, which sets
`original.calibration.x_min = 0.1` and asserts on it — change both lines to
use `sensitivity_x = 0.04`.

- [ ] **Step 2: Write the failing mouse-controller tests**

Replace the whole of `tests/test_mouse_controller.py` with:

```python
import pytest

from facemesh_mouse.config import AppConfig, CalibrationConfig
from facemesh_mouse.mouse_controller import MouseController, accelerate


class FakeMouse:
    def __init__(self, start=(500, 500)):
        self.position = start


def _config(sensitivity_x=0.025, sensitivity_y=0.05, acceleration=0.0, motion_threshold_px=0.0):
    return AppConfig(
        calibration=CalibrationConfig(
            sensitivity_x=sensitivity_x,
            sensitivity_y=sensitivity_y,
            acceleration=acceleration,
            motion_threshold_px=motion_threshold_px,
        ),
        gestures={},
    )


def test_accelerate_returns_zero_for_zero_movement():
    assert accelerate(0.0, 0.5) == 0.0


def test_accelerate_preserves_sign():
    assert accelerate(-0.05, 0.5) < 0
    assert accelerate(0.05, 0.5) > 0


def test_accelerate_with_zero_acceleration_is_linear():
    """|d * 5| ** 0 == 1, so the curve collapses to a pass-through."""
    assert accelerate(0.037, 0.0) == pytest.approx(0.037)


def test_acceleration_damps_small_movements_more_than_large_ones():
    """The whole point of the curve: fine movements get quieter while big
    ones stay fast."""
    small, large = 0.01, 0.2

    small_ratio = accelerate(small, 0.5) / small
    large_ratio = accelerate(large, 0.5) / large

    assert small_ratio < large_ratio


def test_move_cursor_applies_sensitivity_and_screen_scale():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    # movement of 4 camera px * 0.025 sensitivity = 0.1 -> 100px of a 1000px screen
    controller.move_cursor(4.0, 0.0)

    # negative on x: the preview frame is mirrored
    assert mouse.position[0] == pytest.approx(400, abs=1)
    assert mouse.position[1] == pytest.approx(500, abs=1)


def test_move_cursor_y_is_not_inverted():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    controller.move_cursor(0.0, 2.0)  # 2 * 0.05 = 0.1 -> +100px

    assert mouse.position[1] == pytest.approx(600, abs=1)


def test_motion_threshold_zeroes_a_small_movement():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(acceleration=0.0, motion_threshold_px=50.0), (1000, 1000), mouse=mouse
    )
    controller.reanchor()

    controller.move_cursor(0.4, 0.0)  # 0.4 * 0.025 * 1000 = 10px, under the 50px threshold

    assert mouse.position == (500, 500)


def test_cursor_is_clamped_to_the_screen():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    controller.move_cursor(1000.0, 1000.0)

    assert 0 <= mouse.position[0] <= 999
    assert 0 <= mouse.position[1] <= 999


def test_reanchor_resyncs_to_the_real_os_cursor():
    mouse = FakeMouse(start=(300, 400))
    controller = MouseController(_config(), (1000, 1000), mouse=mouse)

    controller.reanchor()

    assert controller._cursor_x == 300
    assert controller._cursor_y == 400
```

- [ ] **Step 3: Run both to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_config.py tests/test_mouse_controller.py -v`
Expected: FAIL — `TypeError: CalibrationConfig.__init__() got an unexpected keyword argument 'sensitivity_x'` and `ImportError: cannot import name 'accelerate'`

- [ ] **Step 4: Replace `CalibrationConfig` and its merge**

In `src/facemesh_mouse/config.py`, replace the dataclass:

```python
@dataclass
class CalibrationConfig:
    x_min: float = 0.35
    x_max: float = 0.65
    y_min: float = 0.35
    y_max: float = 0.65
    smoothing: float = 0.7  # weight kept from the previous smoothed sample
    deadzone_px: float = 4.0  # ignore scaled movement below this many screen pixels
    sensitivity: float = 1.0  # multiplier on the calibration-derived cursor scale
```

with:

```python
@dataclass
class CalibrationConfig:
    """Cursor tuning. Vertical sensitivity is twice horizontal because heads
    travel less vertically than horizontally."""

    sensitivity_x: float = 0.025
    sensitivity_y: float = 0.05
    acceleration: float = 0.5  # 0 = linear; higher damps small movements harder
    motion_threshold_px: float = 0.0  # cursor movement below this is dropped
```

and in `load_config`, replace the `calibration = CalibrationConfig(...)` block with:

```python
    raw_cal = raw.get("calibration", {})
    calibration = CalibrationConfig(
        sensitivity_x=float(raw_cal.get("sensitivity_x", default.calibration.sensitivity_x)),
        sensitivity_y=float(raw_cal.get("sensitivity_y", default.calibration.sensitivity_y)),
        acceleration=float(raw_cal.get("acceleration", default.calibration.acceleration)),
        motion_threshold_px=float(
            raw_cal.get("motion_threshold_px", default.calibration.motion_threshold_px)
        ),
    )
```

Pre-optical-flow keys (`x_min`, `x_max`, `y_min`, `y_max`, `smoothing`,
`deadzone_px`, `sensitivity`) are simply not read, so they fall away on the
next save. Add a brief comment saying so and why no migration is attempted
(four-point bounds have no sensitivity equivalent).

- [ ] **Step 5: Rewrite `mouse_controller.py`**

Replace the whole file with:

```python
"""Cursor movement math + action execution via pynput.

The acceleration curve damps small movements hard while leaving large ones
fast, which stabilizes the cursor without an averaging filter's latency --
each frame's output depends only on that frame's input.

The pure math (`accelerate`, `clamp`) is separated from the pynput-driving
`MouseController` so it can be unit tested without a real display or OS
mouse.
"""
from __future__ import annotations

from pynput.mouse import Button, Controller

from .config import AppConfig

_ACTIONS = {
    "left_click": lambda m: m.click(Button.left, 1),
    "right_click": lambda m: m.click(Button.right, 1),
    "double_click": lambda m: m.click(Button.left, 2),
    "scroll_up": lambda m: m.scroll(0, 1),
    "scroll_down": lambda m: m.scroll(0, -1),
    "none": lambda m: None,
}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def accelerate(delta: float, acceleration: float) -> float:
    """Power curve: small movements shrink far more than large ones, so
    holding still is genuinely still and fine positioning is possible while
    big movements stay fast. `acceleration` of 0 is a linear pass-through."""
    return delta * (abs(delta * 5.0) ** acceleration)


class MouseController:
    def __init__(self, config: AppConfig, screen_size: tuple[int, int], mouse=None) -> None:
        self._config = config
        self._screen_w, self._screen_h = screen_size
        self._mouse = mouse if mouse is not None else Controller()
        self._cursor_x: float | None = None
        self._cursor_y: float | None = None

    def update_config(self, config: AppConfig) -> None:
        self._config = config

    def reanchor(self) -> None:
        """Resyncs to the real OS cursor position, so a cursor moved by a
        physical mouse while paused is not fought on resume."""
        cur_x, cur_y = self._mouse.position
        self._cursor_x = float(cur_x)
        self._cursor_y = float(cur_y)

    def move_cursor(self, movement_x: float, movement_y: float) -> None:
        """Applies one frame of averaged point movement, in camera pixels."""
        cal = self._config.calibration

        delta_x = accelerate(movement_x * cal.sensitivity_x, cal.acceleration)
        delta_y = accelerate(movement_y * cal.sensitivity_y, cal.acceleration)

        # Threshold after the curve, so its unit is honestly "screen pixels
        # of cursor movement" rather than pixels before a curve is applied.
        if abs(delta_x * self._screen_w) < cal.motion_threshold_px:
            delta_x = 0.0
        if abs(delta_y * self._screen_h) < cal.motion_threshold_px:
            delta_y = 0.0

        # Minus on x: the preview frame is mirrored, so moving your head
        # right moves the tracked points left in camera space.
        self._cursor_x = clamp(
            self._cursor_x - delta_x * self._screen_w, 0, self._screen_w - 1
        )
        self._cursor_y = clamp(
            self._cursor_y + delta_y * self._screen_h, 0, self._screen_h - 1
        )
        self._mouse.position = (int(self._cursor_x), int(self._cursor_y))

    def fire_action(self, gesture_name: str) -> None:
        action = self._config.gestures[gesture_name].action
        _ACTIONS[action](self._mouse)
```

- [ ] **Step 6: Wire the point tracker into `engine.py`**

Add the imports:

```python
import cv2
import numpy as np
```

(`cv2` is already imported; add `numpy as np` only if the landmark
conversion below needs it — it does not, so leave imports alone apart from
the new module.)

```python
from .point_tracker import PointTracker
```

In `Engine.__init__`, alongside the other members:

```python
        self._point_tracker = PointTracker()
```

In `Engine.start`, nothing changes.

Replace `_run`'s body from `frame, metrics = self._tracker.process(frame)` through the end of the loop with:

```python
            frame, metrics = self._tracker.process(frame)
            self.state.update(frame, metrics)

            if metrics is None:
                self.no_face.set()
                self._was_active = False
                self._point_tracker.reset()
                continue
            self.no_face.clear()

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            height, width = gray.shape[:2]
            nose = (metrics.nose_x * width, metrics.nose_y * height)
            head_size = _head_size_px(metrics, width, height)
            candidates = _seed_candidates(metrics, width, height)
            self._point_tracker.update(gray, nose, head_size, candidates)

            self._drive_control(metrics)
```

and replace `_drive_control` with:

```python
    def _drive_control(self, metrics: FaceMetrics) -> None:
        """Drives the cursor/gestures for one frame with a face detected.
        Reanchors whenever the previous frame did not drive the cursor --
        covers startup, resume-from-pause, and face-reacquired uniformly."""
        active_now = self.control_enabled.is_set() and not self.paused.is_set()
        if active_now:
            if not self._was_active:
                self._mouse_controller.reanchor()
            self._mouse_controller.move_cursor(*self._point_tracker.get_movement())
            for gesture_name in self._gesture_engine.evaluate(metrics):
                self._mouse_controller.fire_action(gesture_name)
        self._was_active = active_now
```

Then add these two module-level helpers to `engine.py`, below the imports:

```python
# Landmarks seeded as tracking points: the two nostrils and the midpoint
# between the eyes.
_SEED_LANDMARKS = (98, 327, 168)


def _seed_candidates(metrics: FaceMetrics, width: int, height: int) -> list[tuple[float, float]]:
    return [
        (metrics.landmarks[index][0] * width, metrics.landmarks[index][1] * height)
        for index in _SEED_LANDMARKS
        if index < len(metrics.landmarks)
    ]


def _head_size_px(metrics: FaceMetrics, width: int, height: int) -> float:
    """Outer-eye-corner distance in pixels, used as the radius of the
    region beyond which tracked points are culled."""
    left = metrics.landmarks[EYE_OUTER_A]
    right = metrics.landmarks[EYE_OUTER_B]
    return float(
        ((left[0] - right[0]) * width) ** 2 + ((left[1] - right[1]) * height) ** 2
    ) ** 0.5
```

and import the landmark constants at the top of `engine.py`:

```python
from .tracker import EYE_OUTER_A, EYE_OUTER_B, FaceMetrics, FaceTracker
```

- [ ] **Step 7: Update the engine tests for the new call shape**

In `tests/test_engine.py`, the existing tests assert on `reanchor` and
`move_cursor` calls. `reanchor` now takes no arguments and `move_cursor`
takes two floats, but the tests use `MagicMock`, so the assertions that
only check call counts still hold. Add `engine._point_tracker = MagicMock()`
with `engine._point_tracker.get_movement.return_value = (0.0, 0.0)` to
`_engine_with_fakes()` so `_drive_control` has a movement source.

- [ ] **Step 8: Update `calibration_panel.py`'s field references**

The panel still reads `deadzone_px` and `sensitivity`, which no longer
exist. Task 3 rebuilds this file completely; for now, make the smallest
change that keeps it importable and the suite green: point its two sliders
at `motion_threshold_px` (range 0–10) and `sensitivity_x` (range
0.005–0.10), updating the labels and the value-formatting helpers to match.
Leave the capture buttons alone — Task 3 removes them.

Update `tests/test_panels.py`'s `test_sliders_write_into_the_config`
accordingly.

- [ ] **Step 9: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 10: Verify the app starts**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/*.py`
Expected: clean

- [ ] **Step 11: Commit**

```bash
git add src/facemesh_mouse tests/
git commit -m "feat(tracking): drive the cursor from averaged optical-flow movement"
```

---

### Task 3: Movimento tab, window sizing, docs

**Files:**
- Rewrite: `src/facemesh_mouse/calibration_panel.py`
- Modify: `src/facemesh_mouse/config_gui.py`
- Modify: `tests/test_panels.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the four `CalibrationConfig` fields from Task 2.
- Produces: `CalibrationPanel(parent, config)` keeping `.frame` and `.update(metrics)` (now a no-op) so the shell's wiring is unchanged. `cancel_capture()` is **removed**.

- [ ] **Step 1: Write the failing tests**

In `tests/test_panels.py`, replace every existing `CalibrationPanel` test
(the capture ones and the slider one) with:

```python
def test_calibration_panel_builds(container):
    panel = CalibrationPanel(container, default_config())
    panel.frame.pack()
    container.update()

    assert panel.frame.winfo_exists()


def test_calibration_panel_has_a_slider_per_tuning_field(container):
    panel = CalibrationPanel(container, default_config())

    assert set(panel.sliders) == {
        "sensitivity_x",
        "sensitivity_y",
        "acceleration",
        "motion_threshold_px",
    }


def test_sliders_write_their_field_into_the_config(container):
    config = default_config()
    panel = CalibrationPanel(container, config)

    panel.sliders["sensitivity_x"].set(0.08)
    panel.sliders["acceleration"].set(0.9)
    panel.apply_to_config()

    assert config.calibration.sensitivity_x == pytest.approx(0.08, abs=1e-3)
    assert config.calibration.acceleration == pytest.approx(0.9, abs=1e-3)


def test_sliders_start_from_the_configs_values(container):
    config = default_config()
    config.calibration.sensitivity_y = 0.07

    panel = CalibrationPanel(container, config)

    assert panel.sliders["sensitivity_y"].get() == pytest.approx(0.07, abs=1e-3)


def test_update_is_a_no_op(container):
    panel = CalibrationPanel(container, default_config())
    panel.update(_metrics())  # nothing on this tab is live any more

    assert panel.frame.winfo_exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_panels.py -v`
Expected: FAIL with `AttributeError: 'CalibrationPanel' object has no attribute 'sliders'`

- [ ] **Step 3: Rewrite `calibration_panel.py`**

Replace the whole file. Requirements:

- Module docstring explaining the tab now holds cursor tuning.
- `from __future__ import annotations` first.
- `SLIDER_SPECS`: an ordered mapping of field name →
  `(label, from_, to, description)` with these exact values:
  - `sensitivity_x` — "Sensibilidade horizontal", 0.005, 0.10, "Quanto o cursor anda para cada movimento horizontal da cabeça."
  - `sensitivity_y` — "Sensibilidade vertical", 0.005, 0.10, "Quanto o cursor anda para cada movimento vertical da cabeça. Costuma precisar ser maior que a horizontal, porque a cabeça se move menos na vertical."
  - `acceleration` — "Aceleração", 0.0, 1.0, "Deixa o cursor mais lento em movimentos pequenos e mais rápido em movimentos grandes. É o que permite mirar com precisão sem perder velocidade."
  - `motion_threshold_px` — "Limiar de movimento", 0.0, 10.0, "Ignora movimentos menores que isso, em pixels. Ajuda o cursor a parar completamente."
- `CalibrationPanel.__init__(self, parent, config)` builds `self.frame`
  (a `CTkFrame`) and `self.sliders: dict[str, ctk.CTkSlider]`, one row per
  spec: a bold label, the slider, a live value label, and the description in
  a muted color, wrapped at 380 px.
- Each slider starts at the config's current value and updates its value
  label live via its `command`. Give the sliders a bounded width
  (`width=220`) rather than letting them stretch — unbounded stretching is
  what made the window content exceed the screen.
- `apply_to_config()` writes every slider's value into
  `config.calibration`, rounding sensitivities to 4 decimals and
  `motion_threshold_px` to 1.
- `update(self, metrics) -> None` is a no-op with a comment saying the tab
  has no live readouts any more; the shell calls it every frame.
- No capture buttons, no recording state, no `cancel_capture`.
- All strings in Portuguese **with diacritics**.

- [ ] **Step 4: Update the shell**

In `src/facemesh_mouse/config_gui.py`:

- `_start_and_hide` currently calls `self._calibration.cancel_capture()`.
  Replace that line with `self._calibration.apply_to_config()`, keeping it
  before the `save_config` call.
- Change the window sizing set in `_build_widgets` to
  `self._root.geometry("1060x680")` and `self._root.minsize(1000, 620)`.
  With the capture-button grid gone and the sliders bounded, the content
  fits; the previous values were sized around content that overflowed.

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 6: Update the README**

- The "Rodar" walkthrough describes calibrating by recording four extremes.
  Replace that with the slider model: the cursor moves relatively, like a
  mouse, and the Movimento tab tunes horizontal/vertical sensitivity,
  acceleration, and the motion threshold. Keep the gesture and start
  guidance as-is.
- Add the new spec to the design-doc link line.

- [ ] **Step 7: Commit**

```bash
git add src/facemesh_mouse tests/ README.md
git commit -m "feat(gui): replace calibration capture with cursor tuning sliders"
```

---

## Self-Review Notes

- **Spec coverage:** point tracker with seeding/pruning/averaging → Task 1; pruning order enforced by `prune_points`'s internal order and asserted by its tests → Task 1; acceleration curve, per-axis sensitivity, post-acceleration threshold, EMA removal → Task 2; config schema swap with no calibration migration but gesture migration intact → Task 2; engine wiring incl. `reset()` on face loss → Task 2; four sliders, `cancel_capture` removal, window sizing fix → Task 3; attribution → Tasks 1, 2, 3 (module docstrings + README).
- **Placeholder scan:** Task 3 Step 3 specifies the file by requirement rather than literal code because it is a straightforward panel following `gesture_panel.py`'s established row pattern; every string, field name, range, and behavior is given exactly.
- **Type/name consistency:** `prune_points`/`should_add_point`/`mean_movement` signatures match between Task 1's definitions, its tests, and `PointTracker`'s use. `move_cursor(movement_x, movement_y)` and `reanchor()` match between Task 2's controller, its tests, and the engine call site. The four `CalibrationConfig` field names match across Tasks 2 and 3 and both test files.
- **Runnability:** Task 1 adds an unimported module. Task 2 changes the cursor path atomically, including the one-line panel field fix that keeps the GUI importable. Task 3 rebuilds the tab.
- **Out of scope, absent from every task:** head-tilt blending, dwell clicking, OneEuroFilter, click-to-add-points, debug overlays, and any change to gestures, tray, hotkeys, or the single-instance guard.
