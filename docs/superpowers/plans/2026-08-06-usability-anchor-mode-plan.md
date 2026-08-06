# Usability, Anchor Mode & Deadzone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace absolute nose-position cursor mapping with anchor-relative mapping (so pause/resume behaves like lifting and repositioning a physical mouse), add a play/pause calibration capture flow with a deadzone and sensitivity slider, and give the config GUI a full usability pass for a non-technical end user.

**Architecture:** `MouseController` switches from mapping absolute nose position → absolute screen position, to accumulating scaled frame-to-frame nose deltas onto a running cursor position, reset (`reanchor`) whenever tracking control resumes after being inactive (pause, face loss, or startup). `Engine` tracks one `_was_active` bool to detect those resume transitions. `config_gui.py` gets a three-step layout (calibrate → map gestures → start) with toggle-based calibration capture, deadzone/sensitivity sliders, and progress-bar metric readouts.

**Tech Stack:** Python 3.11, tkinter/ttk, pynput, pytest (existing stack, no new dependencies).

## Global Constraints

- UI-facing strings stay in Portuguese, matching the existing `config_gui.py` labels.
- No new hotkeys or gestures — `Ctrl+Alt+P` (existing pause/resume) is reused as the anchor-reset ("lift the mouse") trigger; `Ctrl+Alt+O` is unchanged.
- The EMA `smoothing` config field stays config-file-only in this pass — no new GUI slider for it (explicitly declined during design).
- Default `sensitivity = 1.0` must reproduce the pre-change calibration-only scale exactly — no behavior change for a config that never touches the new slider.
- Deadzone and sensitivity reuse the existing `x_min`/`x_max`/`y_min`/`y_max` calibration fields to derive scale — no calibration JSON field renames.
- Run tests with `.venv\Scripts\python -m pytest tests/ -v` (repo root). `pyproject.toml` already sets `pythonpath = ["src"]`.
- Every module keeps `from __future__ import annotations` as its first import, matching the existing files.
- Pure math stays separated from OS/pynput-driving code in `mouse_controller.py` (existing pattern per its module docstring) so it stays unit-testable without a display.

---

### Task 1: Config schema — deadzone and sensitivity fields

**Files:**
- Modify: `src/facemesh_mouse/config.py:50-56` (`CalibrationConfig`), `src/facemesh_mouse/config.py:100-130` (`load_config`)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `CalibrationConfig.deadzone_px: float = 4.0`, `CalibrationConfig.sensitivity: float = 1.0`, both loaded/saved/merged exactly like the existing `smoothing` field.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_default_config_has_deadzone_and_sensitivity_defaults():
    cfg = config_mod.default_config()
    assert cfg.calibration.deadzone_px == 4.0
    assert cfg.calibration.sensitivity == 1.0


def test_load_config_partial_file_merges_deadzone_and_sensitivity_with_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"calibration": {"deadzone_px": 8.0}}))

    loaded = config_mod.load_config(path)

    assert loaded.calibration.deadzone_px == 8.0
    assert loaded.calibration.sensitivity == config_mod.default_config().calibration.sensitivity


def test_save_then_load_round_trip_includes_deadzone_and_sensitivity(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.calibration.deadzone_px = 6.5
    original.calibration.sensitivity = 1.75

    config_mod.save_config(path, original)
    loaded = config_mod.load_config(path)

    assert loaded.calibration.deadzone_px == 6.5
    assert loaded.calibration.sensitivity == 1.75
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'CalibrationConfig' object has no attribute 'deadzone_px'`

- [ ] **Step 3: Add the fields to `CalibrationConfig`**

In `src/facemesh_mouse/config.py`, replace:

```python
@dataclass
class CalibrationConfig:
    x_min: float = 0.35
    x_max: float = 0.65
    y_min: float = 0.35
    y_max: float = 0.65
    smoothing: float = 0.7  # weight kept from the previous smoothed sample
```

with:

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

- [ ] **Step 4: Merge the fields in `load_config`**

In `src/facemesh_mouse/config.py`, replace:

```python
    raw_cal = raw.get("calibration", {})
    calibration = CalibrationConfig(
        x_min=float(raw_cal.get("x_min", default.calibration.x_min)),
        x_max=float(raw_cal.get("x_max", default.calibration.x_max)),
        y_min=float(raw_cal.get("y_min", default.calibration.y_min)),
        y_max=float(raw_cal.get("y_max", default.calibration.y_max)),
        smoothing=float(raw_cal.get("smoothing", default.calibration.smoothing)),
    )
```

with:

```python
    raw_cal = raw.get("calibration", {})
    calibration = CalibrationConfig(
        x_min=float(raw_cal.get("x_min", default.calibration.x_min)),
        x_max=float(raw_cal.get("x_max", default.calibration.x_max)),
        y_min=float(raw_cal.get("y_min", default.calibration.y_min)),
        y_max=float(raw_cal.get("y_max", default.calibration.y_max)),
        smoothing=float(raw_cal.get("smoothing", default.calibration.smoothing)),
        deadzone_px=float(raw_cal.get("deadzone_px", default.calibration.deadzone_px)),
        sensitivity=float(raw_cal.get("sensitivity", default.calibration.sensitivity)),
    )
```

(`save_config` needs no change — it calls `asdict(config.calibration)`, which already picks up new dataclass fields automatically.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: PASS (all tests, including the 3 new ones)

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/config.py tests/test_config.py
git commit -m "feat(config): add deadzone_px and sensitivity calibration fields"
```

---

### Task 2: Mouse mapping pure functions — `compute_scale`, `apply_deadzone`

**Files:**
- Modify: `src/facemesh_mouse/mouse_controller.py:24-46` (removes `map_normalized_to_screen`, adds new functions)
- Test: `tests/test_mouse_controller.py`

**Interfaces:**
- Consumes: nothing new (pure functions, no config/dataclass dependency).
- Produces: `compute_scale(axis_min: float, axis_max: float, screen_dim: int, sensitivity: float) -> float`, `apply_deadzone(delta: float, scale: float, deadzone_px: float) -> float`. `clamp` and `ema_smooth` are unchanged. `map_normalized_to_screen` is removed — nothing after this task references it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mouse_controller.py` (imports will be fixed in Step 3):

```python
def test_compute_scale_uses_screen_dim_over_axis_range():
    scale = compute_scale(0.3, 0.7, 1000, sensitivity=1.0)
    assert scale == pytest.approx(1000 / 0.4)


def test_compute_scale_sensitivity_multiplies_linearly():
    base = compute_scale(0.3, 0.7, 1000, sensitivity=1.0)
    doubled = compute_scale(0.3, 0.7, 1000, sensitivity=2.0)
    assert doubled == pytest.approx(base * 2)


def test_compute_scale_zero_range_does_not_divide_by_zero():
    scale = compute_scale(0.5, 0.5, 1000, sensitivity=1.0)
    assert scale > 0


def test_apply_deadzone_blocks_small_scaled_delta():
    # |0.001 * 1000| = 1.0px, below the 4px deadzone
    assert apply_deadzone(0.001, scale=1000, deadzone_px=4.0) == 0.0


def test_apply_deadzone_passes_large_scaled_delta_unchanged():
    # |0.01 * 1000| = 10px, above the 4px deadzone
    assert apply_deadzone(0.01, scale=1000, deadzone_px=4.0) == 0.01
```

Update the import line at the top of `tests/test_mouse_controller.py`:

```python
from facemesh_mouse.mouse_controller import (
    apply_deadzone,
    compute_scale,
    ema_smooth,
    map_normalized_to_screen,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_mouse_controller.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_scale' from 'facemesh_mouse.mouse_controller'`

- [ ] **Step 3: Add the new functions (keep the old one for now)**

In `src/facemesh_mouse/mouse_controller.py`, after the `clamp` function, add:

```python
def compute_scale(axis_min: float, axis_max: float, screen_dim: int, sensitivity: float) -> float:
    """How many screen pixels one unit of normalized nose movement covers,
    derived from the calibrated axis range and the user's sensitivity
    multiplier."""
    axis_range = (axis_max - axis_min) or 1e-6
    return (screen_dim / axis_range) * sensitivity


def apply_deadzone(delta: float, scale: float, deadzone_px: float) -> float:
    """Zeroes a raw normalized delta if its scaled (pixel) magnitude falls
    below the deadzone threshold; otherwise returns it unchanged."""
    if abs(delta * scale) < deadzone_px:
        return 0.0
    return delta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_mouse_controller.py -v`
Expected: PASS (all tests, including the 5 new ones and the existing `map_normalized_to_screen`/`ema_smooth` ones)

- [ ] **Step 5: Remove the now-obsolete absolute-mapping function and its tests**

In `src/facemesh_mouse/mouse_controller.py`, delete `map_normalized_to_screen` entirely (it will not be called anywhere after Task 3).

In `tests/test_mouse_controller.py`:
- Remove `map_normalized_to_screen` from the import line.
- Delete these three tests: `test_map_normalized_to_screen_center`, `test_map_normalized_to_screen_clamps_outside_calibration_range`, `test_map_normalized_to_screen_respects_calibration_bounds`.

- [ ] **Step 6: Run the full suite to verify nothing else broke**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS (18 tests: 16 original minus 3 removed plus 5 added)

- [ ] **Step 7: Commit**

```bash
git add src/facemesh_mouse/mouse_controller.py tests/test_mouse_controller.py
git commit -m "refactor(mouse): replace absolute mapping with scale/deadzone pure functions"
```

---

### Task 3: `MouseController` — injectable mouse, `reanchor`, delta-based `move_cursor`

**Files:**
- Modify: `src/facemesh_mouse/mouse_controller.py:57-87` (`MouseController` class)
- Test: `tests/test_mouse_controller.py`

**Interfaces:**
- Consumes: `compute_scale`, `apply_deadzone`, `clamp`, `ema_smooth` (Task 2); `CalibrationConfig.deadzone_px`/`.sensitivity` (Task 1).
- Produces: `MouseController(config: AppConfig, screen_size: tuple[int, int], mouse=None)`, `.reanchor(metrics: FaceMetrics) -> None`, `.move_cursor(metrics: FaceMetrics) -> None` (rewritten, same call signature as before), `.fire_action(gesture_name: str) -> None` (unchanged), `.update_config(config: AppConfig) -> None` (unchanged). **`move_cursor` requires `reanchor` to have been called at least once first** — Task 4 (`Engine`) is responsible for guaranteeing that ordering; calling `move_cursor` before any `reanchor` raises `TypeError` (arithmetic on `None`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mouse_controller.py`:

```python
from facemesh_mouse.config import AppConfig, CalibrationConfig
from facemesh_mouse.mouse_controller import MouseController
from facemesh_mouse.tracker import FaceMetrics


class FakeMouse:
    def __init__(self, start=(500, 500)):
        self.position = start


def _config(sensitivity=1.0, deadzone_px=0.0, smoothing=0.0):
    return AppConfig(
        calibration=CalibrationConfig(
            x_min=0.3,
            x_max=0.7,
            y_min=0.3,
            y_max=0.7,
            smoothing=smoothing,
            deadzone_px=deadzone_px,
            sensitivity=sensitivity,
        ),
        gestures={},
    )


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


def test_reanchor_sets_state_from_current_os_cursor_position():
    mouse = FakeMouse(start=(300, 400))
    controller = MouseController(_config(), (1000, 1000), mouse=mouse)

    controller.reanchor(_metrics(nose_x=0.5, nose_y=0.5))

    assert controller._prev_nose_x == 0.5
    assert controller._prev_nose_y == 0.5
    assert controller._target_x == 300
    assert controller._target_y == 400
    assert controller._smoothed_x == 300
    assert controller._smoothed_y == 400


def test_move_cursor_after_reanchor_applies_scaled_delta_with_no_smoothing():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(sensitivity=1.0, deadzone_px=0.0, smoothing=0.0), (1000, 1000), mouse=mouse
    )
    controller.reanchor(_metrics(nose_x=0.5, nose_y=0.5))

    # scale_x = 1000 / 0.4 = 2500; moving nose by +0.02 -> +50px
    controller.move_cursor(_metrics(nose_x=0.52, nose_y=0.5))

    assert mouse.position[0] == pytest.approx(550, abs=1)
    assert mouse.position[1] == pytest.approx(500, abs=1)


def test_move_cursor_ignores_movement_below_deadzone():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(sensitivity=1.0, deadzone_px=100.0, smoothing=0.0), (1000, 1000), mouse=mouse
    )
    controller.reanchor(_metrics(nose_x=0.5, nose_y=0.5))

    # scale_x = 2500; delta 0.001 -> 2.5px, well under the 100px deadzone
    controller.move_cursor(_metrics(nose_x=0.501, nose_y=0.5))

    assert mouse.position == (500, 500)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_mouse_controller.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'mouse'`

- [ ] **Step 3: Rewrite the `MouseController` class**

In `src/facemesh_mouse/mouse_controller.py`, replace the entire `MouseController` class with:

```python
class MouseController:
    def __init__(self, config: AppConfig, screen_size: tuple[int, int], mouse=None) -> None:
        self._config = config
        self._screen_w, self._screen_h = screen_size
        self._mouse = mouse if mouse is not None else Controller()
        self._prev_nose_x: float | None = None
        self._prev_nose_y: float | None = None
        self._target_x: float | None = None
        self._target_y: float | None = None
        self._smoothed_x: float | None = None
        self._smoothed_y: float | None = None

    def update_config(self, config: AppConfig) -> None:
        self._config = config

    def reanchor(self, metrics: FaceMetrics) -> None:
        """Resets tracking to the real OS cursor position -- called whenever
        control resumes after being inactive (pause, face loss, startup) so
        the cursor never jumps."""
        self._prev_nose_x = metrics.nose_x
        self._prev_nose_y = metrics.nose_y
        cur_x, cur_y = self._mouse.position
        self._target_x = float(cur_x)
        self._target_y = float(cur_y)
        self._smoothed_x = float(cur_x)
        self._smoothed_y = float(cur_y)

    def move_cursor(self, metrics: FaceMetrics) -> None:
        cal = self._config.calibration
        scale_x = compute_scale(cal.x_min, cal.x_max, self._screen_w, cal.sensitivity)
        scale_y = compute_scale(cal.y_min, cal.y_max, self._screen_h, cal.sensitivity)

        dx = metrics.nose_x - self._prev_nose_x
        dy = metrics.nose_y - self._prev_nose_y
        self._prev_nose_x = metrics.nose_x
        self._prev_nose_y = metrics.nose_y

        dx = apply_deadzone(dx, scale_x, cal.deadzone_px)
        dy = apply_deadzone(dy, scale_y, cal.deadzone_px)

        self._target_x = clamp(self._target_x + dx * scale_x, 0, self._screen_w - 1)
        self._target_y = clamp(self._target_y + dy * scale_y, 0, self._screen_h - 1)

        self._smoothed_x = ema_smooth(self._smoothed_x, self._target_x, cal.smoothing)
        self._smoothed_y = ema_smooth(self._smoothed_y, self._target_y, cal.smoothing)
        self._mouse.position = (int(self._smoothed_x), int(self._smoothed_y))

    def fire_action(self, gesture_name: str) -> None:
        action = self._config.gestures[gesture_name].action
        _ACTIONS[action](self._mouse)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_mouse_controller.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/mouse_controller.py tests/test_mouse_controller.py
git commit -m "feat(mouse): anchor-relative cursor mapping with injectable mouse for testing"
```

---

### Task 4: `Engine` — reanchor on resume (pause / face-reacquired / startup)

**Files:**
- Modify: `src/facemesh_mouse/engine.py:41-91` (`Engine.__init__`, `Engine._run`)
- Test: `tests/test_engine.py` (new file)

**Interfaces:**
- Consumes: `MouseController.reanchor`, `.move_cursor`, `.fire_action` (Task 3); `GestureEngine.evaluate` (unchanged, existing).
- Produces: `Engine._was_active: bool`, `Engine._drive_control(metrics: FaceMetrics) -> None`. `Engine`'s public interface (`start`, `update_config`, `control_enabled`, `paused`, `no_face`, `state`, `stop`) is unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_engine.py`:

```python
from unittest.mock import MagicMock

from facemesh_mouse.config import default_config
from facemesh_mouse.engine import Engine
from facemesh_mouse.tracker import FaceMetrics


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


def _engine_with_fakes():
    engine = Engine(default_config())
    engine._mouse_controller = MagicMock()
    engine._gesture_engine = MagicMock()
    engine._gesture_engine.evaluate.return_value = []
    return engine


def test_reanchors_on_first_active_frame():
    engine = _engine_with_fakes()
    engine.control_enabled.set()

    engine._drive_control(_metrics())

    engine._mouse_controller.reanchor.assert_called_once()
    engine._mouse_controller.move_cursor.assert_called_once()


def test_does_not_reanchor_on_subsequent_active_frames():
    engine = _engine_with_fakes()
    engine.control_enabled.set()

    engine._drive_control(_metrics())
    engine._drive_control(_metrics())

    assert engine._mouse_controller.reanchor.call_count == 1
    assert engine._mouse_controller.move_cursor.call_count == 2


def test_reanchors_on_resume_from_pause():
    engine = _engine_with_fakes()
    engine.control_enabled.set()

    engine._drive_control(_metrics())  # active frame 1 -> reanchor #1
    engine.paused.set()
    engine._drive_control(_metrics())  # paused, no-op
    engine.paused.clear()
    engine._drive_control(_metrics())  # resumed -> reanchor #2

    assert engine._mouse_controller.reanchor.call_count == 2


def test_reanchors_after_face_reacquired():
    engine = _engine_with_fakes()
    engine.control_enabled.set()

    engine._drive_control(_metrics())  # active -> reanchor #1
    engine._was_active = False  # simulates the no-face frame's reset
    engine._drive_control(_metrics())  # face reacquired -> reanchor #2

    assert engine._mouse_controller.reanchor.call_count == 2


def test_paused_frame_does_not_move_cursor_or_evaluate_gestures():
    engine = _engine_with_fakes()
    engine.control_enabled.set()
    engine.paused.set()

    engine._drive_control(_metrics())

    engine._mouse_controller.move_cursor.assert_not_called()
    engine._gesture_engine.evaluate.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_engine.py -v`
Expected: FAIL with `AttributeError: 'Engine' object has no attribute '_drive_control'`

- [ ] **Step 3: Add `_was_active` and `_drive_control`, update `_run`**

In `src/facemesh_mouse/engine.py`, in `Engine.__init__`, add after `self._mouse_controller: MouseController | None = None`:

```python
        self._was_active = False
```

Replace the `_run` method:

```python
    def _run(self) -> None:
        while not self._stop.is_set():
            ok, frame = self._camera.read()
            if not ok:
                time.sleep(0.05)
                continue

            frame, metrics = self._tracker.process(frame)
            self.state.update(frame, metrics)

            if metrics is None:
                self.no_face.set()
                self._was_active = False
                continue
            self.no_face.clear()

            self._drive_control(metrics)
```

with:

```python
    def _run(self) -> None:
        while not self._stop.is_set():
            ok, frame = self._camera.read()
            if not ok:
                time.sleep(0.05)
                continue

            frame, metrics = self._tracker.process(frame)
            self.state.update(frame, metrics)

            if metrics is None:
                self.no_face.set()
                self._was_active = False
                continue
            self.no_face.clear()

            self._drive_control(metrics)

    def _drive_control(self, metrics: FaceMetrics) -> None:
        """Drives the cursor/gestures for one frame with a face detected.
        Reanchors whenever the previous frame did not drive the cursor --
        covers startup, resume-from-pause, and face-reacquired uniformly."""
        active_now = self.control_enabled.is_set() and not self.paused.is_set()
        if active_now:
            if not self._was_active:
                self._mouse_controller.reanchor(metrics)
            self._mouse_controller.move_cursor(metrics)
            for gesture_name in self._gesture_engine.evaluate(metrics):
                self._mouse_controller.fire_action(gesture_name)
        self._was_active = active_now
```

(Note: the "before" block above already shows the target shape for the part that doesn't change — only add the new `_drive_control` method; the body of `_run` itself is unchanged from what's currently in the file except it already calls into what's now split out. Concretely: in the real file, delete the four lines inside the old `if self.control_enabled.is_set() and not self.paused.is_set():` block and the loop that follow `self.no_face.clear()`, and replace them with a single `self._drive_control(metrics)` call, then add `_drive_control` as a new method below `_run`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_engine.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/engine.py tests/test_engine.py
git commit -m "feat(engine): reanchor cursor on resume from pause, face reacquired, and startup"
```

---

### Task 5: Config GUI — play/pause capture, deadzone/sensitivity sliders, progress-bar metrics, numbered steps

**Files:**
- Modify: `src/facemesh_mouse/config_gui.py` (full rewrite of `ConfigWindow`)
- Modify: `README.md:31-44` ("Rodar" section)

**Interfaces:**
- Consumes: `CalibrationConfig.deadzone_px`/`.sensitivity` (Task 1). Does not depend on Tasks 2-4's `MouseController`/`Engine` internals — the GUI only reads/writes `AppConfig` fields and the existing `Engine.state.snapshot()` preview API, both unchanged in shape.
- Produces: no new interface consumed elsewhere — this is the top of the call graph for this plan.

No automated tests: this project doesn't unit-test the Tkinter GUI (see original design spec's testing section — camera/mouse/tray/hotkeys/GUI are manual-checklist only). Verification here is a `py_compile` syntax check plus a manual run-through.

- [ ] **Step 1: Replace `src/facemesh_mouse/config_gui.py` in full**

```python
"""Tkinter config window: webcam preview + calibration wizard + gesture
mapping form. Reads the engine's SharedState for preview only -- it never
touches the camera directly (see engine.py)."""
from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk
from typing import Callable

import cv2
from PIL import Image, ImageDraw, ImageTk

from . import config as config_mod
from .config import AppConfig
from .engine import Engine

_GESTURE_LABELS = {
    "blink_left": "Piscar olho A",
    "blink_right": "Piscar olho B",
    "blink_both": "Piscar os dois",
    "mouth_open": "Boca aberta",
    "eyebrow_raised": "Sobrancelha levantada",
}

_ACTION_LABELS = {
    "none": "(nenhuma)",
    "left_click": "Clique esquerdo",
    "right_click": "Clique direito",
    "double_click": "Duplo clique",
    "scroll_up": "Scroll cima",
    "scroll_down": "Scroll baixo",
}
_ACTION_BY_LABEL = {v: k for k, v in _ACTION_LABELS.items()}

_CAPTURE_META = {
    "up": {
        "axis": "y",
        "extreme": "min",
        "label": "Cima",
        "guide": "Mova a cabeça o máximo para cima e clique em Parar quando terminar.",
    },
    "down": {
        "axis": "y",
        "extreme": "max",
        "label": "Baixo",
        "guide": "Mova a cabeça o máximo para baixo e clique em Parar quando terminar.",
    },
    "left": {
        "axis": "x",
        "extreme": "min",
        "label": "Esquerda",
        "guide": "Mova a cabeça o máximo para a esquerda e clique em Parar quando terminar.",
    },
    "right": {
        "axis": "x",
        "extreme": "max",
        "label": "Direita",
        "guide": "Mova a cabeça o máximo para a direita e clique em Parar quando terminar.",
    },
}

_METRIC_TO_GESTURE = {
    "ear_a": "blink_left",
    "ear_b": "blink_right",
    "mouth_open_ratio": "mouth_open",
    "eyebrow_raise_ratio": "eyebrow_raised",
}
_METRIC_BAR_LABELS = {
    "ear_a": "Olho A",
    "ear_b": "Olho B",
    "mouth_open_ratio": "Boca aberta",
    "eyebrow_raise_ratio": "Sobrancelha levantada",
}


class ConfigWindow:
    def __init__(
        self,
        root: tk.Tk,
        engine: Engine,
        config: AppConfig,
        config_path: str,
        on_start: Callable[[AppConfig], None],
    ) -> None:
        self._root = root
        self._engine = engine
        self._config = copy.deepcopy(config)
        self._config_path = config_path
        self._on_start = on_start
        self._tk_image = None
        self._after_id = None

        self._recording_direction: str | None = None
        self._recording_extreme: float | None = None
        self._capture_buttons: dict[str, ttk.Button] = {}

        root.title("FaceMesh Mouse - Configuracao")
        root.protocol("WM_DELETE_WINDOW", self._start_and_hide)

        self._build_widgets()
        self._tick()

    # -- widgets ----------------------------------------------------
    def _build_widgets(self) -> None:
        main = ttk.Frame(self._root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        self._canvas = tk.Label(main)
        self._canvas.grid(row=0, column=0, rowspan=30, padx=(0, 10), sticky="n")

        row = 0
        row = self._build_step1_calibration(main, row)
        row = self._build_step2_gestures(main, row)
        row = self._build_step3_start(main, row)

    def _section_header(self, main: ttk.Frame, row: int, text: str) -> int:
        ttk.Label(main, text=text, font=("Segoe UI", 10, "bold")).grid(
            row=row, column=1, sticky="w", pady=(10, 2)
        )
        return row + 1

    def _help_text(self, main: ttk.Frame, row: int, text: str) -> int:
        ttk.Label(main, text=text, justify="left", wraplength=320).grid(
            row=row, column=1, sticky="w", pady=(0, 4)
        )
        return row + 1

    # -- step 1: calibration ------------------------------------------
    def _build_step1_calibration(self, main: ttk.Frame, row: int) -> int:
        row = self._section_header(main, row, "1. Calibrar movimento")
        row = self._help_text(
            main,
            row,
            "Grave os 4 extremos do movimento da cabeça: aperte Gravar, mova "
            "a cabeça até o limite desejado e aperte Parar. Ajuste as barras "
            "abaixo se o cursor estiver muito sensível ou tremendo.",
        )

        cal_frame = ttk.Frame(main)
        cal_frame.grid(row=row, column=1, sticky="w")
        for col, direction in enumerate(["up", "down", "left", "right"]):
            btn = ttk.Button(
                cal_frame,
                text=f"▶ Gravar {_CAPTURE_META[direction]['label']}",
                command=lambda d=direction: self._toggle_capture(d),
            )
            btn.grid(row=col // 2, column=col % 2, padx=2, pady=2, sticky="w")
            self._capture_buttons[direction] = btn
        row += 1

        self._capture_guide = tk.StringVar(value="")
        ttk.Label(main, textvariable=self._capture_guide, justify="left", wraplength=320).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        self._capture_live = tk.StringVar(value="")
        ttk.Label(main, textvariable=self._capture_live).grid(row=row, column=1, sticky="w")
        row += 1

        self._cal_status = tk.StringVar(value=self._calibration_status_text())
        ttk.Label(main, textvariable=self._cal_status, justify="left").grid(
            row=row, column=1, sticky="w", pady=(0, 8)
        )
        row += 1

        self._deadzone_var = tk.DoubleVar(value=self._config.calibration.deadzone_px)
        ttk.Label(main, text="Zona morta (ignora tremores pequenos):").grid(
            row=row, column=1, sticky="w"
        )
        row += 1
        deadzone_row = ttk.Frame(main)
        deadzone_row.grid(row=row, column=1, sticky="w")
        ttk.Scale(
            deadzone_row,
            from_=0,
            to=15,
            orient="horizontal",
            length=180,
            variable=self._deadzone_var,
            command=self._on_deadzone_change,
        ).grid(row=0, column=0)
        self._deadzone_label = ttk.Label(deadzone_row, text=self._deadzone_text())
        self._deadzone_label.grid(row=0, column=1, padx=(6, 0))
        row += 1

        self._sensitivity_var = tk.DoubleVar(value=self._config.calibration.sensitivity)
        ttk.Label(main, text="Sensibilidade (velocidade do cursor):").grid(
            row=row, column=1, sticky="w", pady=(6, 0)
        )
        row += 1
        sensitivity_row = ttk.Frame(main)
        sensitivity_row.grid(row=row, column=1, sticky="w")
        ttk.Scale(
            sensitivity_row,
            from_=0.3,
            to=3.0,
            orient="horizontal",
            length=180,
            variable=self._sensitivity_var,
            command=self._on_sensitivity_change,
        ).grid(row=0, column=0)
        self._sensitivity_label = ttk.Label(sensitivity_row, text=self._sensitivity_text())
        self._sensitivity_label.grid(row=0, column=1, padx=(6, 0))
        row += 1

        return row

    def _calibration_status_text(self) -> str:
        cal = self._config.calibration
        return (
            f"x: [{cal.x_min:.2f}, {cal.x_max:.2f}]  "
            f"y: [{cal.y_min:.2f}, {cal.y_max:.2f}]"
        )

    def _deadzone_text(self) -> str:
        return f"{self._config.calibration.deadzone_px:.0f}px"

    def _sensitivity_text(self) -> str:
        return f"{self._config.calibration.sensitivity:.1f}x"

    def _on_deadzone_change(self, _value=None) -> None:
        self._config.calibration.deadzone_px = round(self._deadzone_var.get(), 1)
        self._deadzone_label.configure(text=self._deadzone_text())

    def _on_sensitivity_change(self, _value=None) -> None:
        self._config.calibration.sensitivity = round(self._sensitivity_var.get(), 2)
        self._sensitivity_label.configure(text=self._sensitivity_text())

    # -- calibration capture (play/pause) ------------------------------
    def _toggle_capture(self, direction: str) -> None:
        if self._recording_direction == direction:
            self._stop_capture()
        else:
            self._start_capture(direction)

    def _start_capture(self, direction: str) -> None:
        _frame, metrics = self._engine.state.snapshot()
        if metrics is None:
            return
        meta = _CAPTURE_META[direction]
        seed = metrics.nose_y if meta["axis"] == "y" else metrics.nose_x
        self._recording_direction = direction
        self._recording_extreme = seed
        for d, btn in self._capture_buttons.items():
            if d == direction:
                btn.configure(text="⏸ Parar")
            else:
                btn.configure(state="disabled")
        self._capture_guide.set(meta["guide"])
        self._update_live_extreme_label()

    def _stop_capture(self) -> None:
        if self._recording_direction is None:
            return
        direction = self._recording_direction
        cal = self._config.calibration
        if direction == "up":
            cal.y_min = self._recording_extreme
        elif direction == "down":
            cal.y_max = self._recording_extreme
        elif direction == "left":
            cal.x_min = self._recording_extreme
        elif direction == "right":
            cal.x_max = self._recording_extreme

        self._recording_direction = None
        self._recording_extreme = None
        for d, btn in self._capture_buttons.items():
            btn.configure(state="normal", text=f"▶ Gravar {_CAPTURE_META[d]['label']}")
        self._capture_guide.set("")
        self._capture_live.set("")
        self._cal_status.set(self._calibration_status_text())

    def _update_live_extreme_label(self) -> None:
        if self._recording_direction is None:
            return
        self._capture_live.set(f"Extremo atual: {self._recording_extreme:.3f}")

    # -- step 2: gesture mapping ---------------------------------------
    def _build_step2_gestures(self, main: ttk.Frame, row: int) -> int:
        row = self._section_header(main, row, "2. Mapear gestos")
        row = self._help_text(
            main,
            row,
            "Pisque cada olho e observe qual barra reage abaixo antes de "
            "mapear (rótulo 'A'/'B' é só interno). Escolha o que cada gesto "
            "faz; '(nenhuma)' desativa o gesto.",
        )

        self._metric_bar_vars: dict[str, tk.DoubleVar] = {}
        for key in ["ear_a", "ear_b", "mouth_open_ratio", "eyebrow_raise_ratio"]:
            bar_row = ttk.Frame(main)
            bar_row.grid(row=row, column=1, sticky="w", pady=1)
            ttk.Label(bar_row, text=_METRIC_BAR_LABELS[key], width=18).grid(row=0, column=0)
            var = tk.DoubleVar(value=0.0)
            self._metric_bar_vars[key] = var
            ttk.Progressbar(
                bar_row,
                orient="horizontal",
                length=150,
                mode="determinate",
                maximum=100,
                variable=var,
            ).grid(row=0, column=1)
            row += 1

        self._action_vars: dict[str, tk.StringVar] = {}
        for gesture_name in config_mod.GESTURE_NAMES:
            gframe = ttk.Frame(main)
            gframe.grid(row=row, column=1, sticky="w", pady=2)
            ttk.Label(gframe, text=_GESTURE_LABELS[gesture_name], width=22).grid(row=0, column=0)
            current_action = self._config.gestures[gesture_name].action
            var = tk.StringVar(value=_ACTION_LABELS[current_action])
            self._action_vars[gesture_name] = var
            combo = ttk.Combobox(
                gframe,
                textvariable=var,
                values=list(_ACTION_LABELS.values()),
                state="readonly",
                width=18,
            )
            combo.grid(row=0, column=1)
            row += 1

        return row

    # -- step 3: start ---------------------------------------------------
    def _build_step3_start(self, main: ttk.Frame, row: int) -> int:
        row = self._section_header(main, row, "3. Iniciar")
        row = self._help_text(
            main,
            row,
            "Ao iniciar, esta janela some e o cursor passa a seguir a "
            "cabeça. Ctrl+Alt+P pausa/retoma a qualquer momento -- use pra "
            "'levantar o mouse': o cursor congela, reposicione a cabeça numa "
            "posição confortável e retome; o controle continua exatamente de "
            "onde parou, sem pular. Ctrl+Alt+O reabre esta janela.",
        )

        ttk.Button(
            main, text="▶ Iniciar controle do mouse", command=self._start_and_hide
        ).grid(row=row, column=1, sticky="e", pady=(6, 0))
        row += 1
        return row

    # -- live preview loop ---------------------------------------------
    def _tick(self) -> None:
        frame, metrics = self._engine.state.snapshot()
        if frame is not None:
            display = frame.copy()
            if metrics is not None:
                self._draw_overlay(display, metrics)
                self._update_metric_bars(metrics)
                if self._recording_direction is not None:
                    self._track_capture_extreme(metrics)
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            self._tk_image = ImageTk.PhotoImage(image=img)
            self._canvas.configure(image=self._tk_image)

        self._after_id = self._root.after(33, self._tick)

    def _update_metric_bars(self, metrics) -> None:
        values = {
            "ear_a": metrics.ear_a,
            "ear_b": metrics.ear_b,
            "mouth_open_ratio": metrics.mouth_open_ratio,
            "eyebrow_raise_ratio": metrics.eyebrow_raise_ratio,
        }
        for key, value in values.items():
            gesture_name = _METRIC_TO_GESTURE[key]
            threshold = self._config.gestures[gesture_name].threshold or 1e-6
            pct = max(0.0, min(100.0, (value / threshold) * 100.0))
            self._metric_bar_vars[key].set(pct)

    def _track_capture_extreme(self, metrics) -> None:
        meta = _CAPTURE_META[self._recording_direction]
        live_value = metrics.nose_y if meta["axis"] == "y" else metrics.nose_x
        if meta["extreme"] == "min":
            self._recording_extreme = min(self._recording_extreme, live_value)
        else:
            self._recording_extreme = max(self._recording_extreme, live_value)
        self._update_live_extreme_label()

    def _draw_overlay(self, frame, metrics) -> None:
        h, w = frame.shape[:2]
        cx, cy = int(metrics.nose_x * w), int(metrics.nose_y * h)
        cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

    # -- lifecycle ----------------------------------------------------
    def _start_and_hide(self) -> None:
        for gesture_name, var in self._action_vars.items():
            self._config.gestures[gesture_name].action = _ACTION_BY_LABEL[var.get()]
        config_mod.save_config(self._config_path, self._config)
        self._on_start(self._config)
        self._root.withdraw()

    def show(self) -> None:
        self._root.deiconify()
        self._root.lift()
```

- [ ] **Step 2: Syntax-check the file**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/config_gui.py`
Expected: no output, exit code 0

- [ ] **Step 3: Run the full automated suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS (unaffected by this GUI-only change, confirms no accidental breakage)

- [ ] **Step 4: Manual verification checklist**

Run: `.venv\Scripts\python run.py`, then with a real webcam:
- Window shows "1. Calibrar movimento" / "2. Mapear gestos" / "3. Iniciar" as three labeled sections.
- Click "▶ Gravar Cima": the button becomes "⏸ Parar", the other 3 capture buttons disable, a guide sentence appears, and "Extremo atual: …" updates live as you move your head. Click "⏸ Parar": value locks in, all 4 buttons re-enable, guide/live text clear, the x/y calibration summary updates. Repeat for Baixo/Esquerda/Direita.
- Dragging the "Zona morta" and "Sensibilidade" sliders updates their px/x labels live.
- In step 2, the 4 progress bars move as you blink/open your mouth/raise your eyebrows.
- Click "▶ Iniciar controle do mouse": window hides, cursor follows head movement.
- Press `Ctrl+Alt+P`: cursor freezes. Move your head to a new comfortable position. Press `Ctrl+Alt+P` again: cursor resumes moving from the same spot with no jump.
- Cover the camera (no face): tray icon goes orange; uncover it: cursor resumes from its current position with no jump.

- [ ] **Step 5: Update the README's "Rodar" section**

In `README.md`, replace:

```markdown
Na primeira execução abre a janela de configuração:

1. Observe os indicadores `ear_a` / `ear_b` / `mouth_open_ratio` /
   `eyebrow_raise_ratio` enquanto faz cada gesto, pra saber qual reage a
   qual olho (os nomes "A"/"B" são só internos, sem relação fixa com
   esquerda/direita anatômica por causa do espelhamento da câmera).
2. Calibre a faixa de movimento: posicione a cabeça em cada extremo
   (cima/baixo/esquerda/direita) e clique em "Capturar".
3. Mapeie cada gesto pra uma ação de mouse no dropdown.
4. Clique em "Iniciar tracking" (ou feche a janela) — a câmera some da
   tela e o controle do mouse fica ativo em background.

Ícone na bandeja: Pausar/Retomar, Reabrir Config, Sair.
Atalhos globais: `Ctrl+Alt+P` pausa/retoma, `Ctrl+Alt+O` reabre a config.
```

with:

```markdown
Na primeira execução abre a janela de configuração, em 3 passos:

1. **Calibrar movimento**: clique em "Gravar Cima/Baixo/Esquerda/Direita",
   mova a cabeça até o extremo desejado e clique em "Parar" — o valor mais
   extremo atingido durante a gravação é o que fica salvo, não precisa
   acertar o timing do clique. Ajuste "Zona morta" (ignora tremores
   pequenos) e "Sensibilidade" (velocidade do cursor) se necessário.
2. **Mapear gestos**: observe as barras `Olho A` / `Olho B` / `Boca aberta`
   / `Sobrancelha levantada` reagirem enquanto faz cada gesto, pra saber
   qual reage a qual olho (os nomes "A"/"B" são só internos, sem relação
   fixa com esquerda/direita anatômica por causa do espelhamento da
   câmera), e escolha uma ação de mouse pra cada gesto no dropdown.
3. **Iniciar**: clique em "Iniciar controle do mouse" (ou feche a janela)
   — a câmera some da tela e o controle do mouse fica ativo em background.

O cursor se move de forma relativa à cabeça, como um mouse físico: `Ctrl+Alt+P`
pausa e congela o cursor a qualquer momento — use pra "levantar o mouse",
reposicionar a cabeça numa posição mais confortável, e retomar exatamente de
onde parou, sem pular.

Ícone na bandeja: Pausar/Retomar, Reabrir Config, Sair.
Atalhos globais: `Ctrl+Alt+P` pausa/retoma, `Ctrl+Alt+O` reabre a config.
```

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/config_gui.py README.md
git commit -m "feat(gui): play/pause calibration capture, deadzone/sensitivity sliders, numbered steps"
```

---

## Self-Review Notes

- **Spec coverage:** anchor-relative mapping → Tasks 2-4; play/pause capture + guide line → Task 5; deadzone → Tasks 1-3, 5; sensitivity slider → Tasks 1, 3, 5; GUI usability pass (steps, help text, progress bars, renamed button, pause/resume callout) → Task 5; testing section (pure delta function tests, reanchor tests, `Engine` reanchor-trigger tests) → Tasks 2-4; manual checklist addition → Task 5 Step 4.
- **Placeholder scan:** no TBD/TODO; every step has literal code or an exact command.
- **Type/name consistency checked:** `compute_scale`/`apply_deadzone` signatures match between Task 2's definition and Task 3's usage; `reanchor`/`move_cursor`/`fire_action` names match between Task 3's class and Task 4's `_drive_control`; `deadzone_px`/`sensitivity` field names match across Tasks 1, 3, and 5's slider handlers.
- **Out of scope, confirmed absent from all tasks:** exposed smoothing slider, multi-monitor calibration, a separate recenter-without-pause action.
