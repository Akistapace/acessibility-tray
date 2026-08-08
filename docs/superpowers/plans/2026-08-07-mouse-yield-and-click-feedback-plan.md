# Mouse Yield, Click Feedback & Click Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The app yields cursor control to a physical mouse touch and auto-resumes after a quiet period, the tray icon shows when that's happening, every gesture-fired action shows a click-through visual pulse at the cursor, and every action is recorded to a local rotating log.

**Architecture:** `MouseController` compares the OS cursor's actual position against the position it last wrote; a divergence means the physical mouse moved it, so it stops applying tracked movement until the cursor has been still for a configurable quiet period, then reanchors. `fire_action` gains an injected `on_action` callback that `main.py` wires to two new standalone modules — `click_feedback.py` (a borderless, click-through `Toplevel` pulse) and `click_log.py` (a stdlib `RotatingFileHandler`) — keeping `MouseController` free of any GUI or filesystem dependency.

**Tech Stack:** Python 3.11, stdlib `logging`/`ctypes` (no new dependencies), existing pynput/CustomTkinter/pytest stack.

## Global Constraints

- `YIELD_DETECT_PX = 2` (OS cursor-position rounding tolerance). Default `yield_resume_after_s = 3.0`, GUI slider range 1.0–10.0.
- Tray icon precedence, highest first: **paused** → **yielded** → **no face** → **running**.
- The click-through overlay recipe is `GetParent(window.winfo_id())` to find the real top-level HWND, then `SetWindowLongW` with `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW` on that HWND. This was verified empirically in this exact environment: `winfo_id()` returns a Tk-internal child window, and only its `GetParent` (already carrying the topmost/toolwindow bits Tk itself set) is the window Windows actually composites. Verifying it visually requires `PrintWindow` with `PW_RENDERFULLCONTENT` (flag value `2`) — a plain `BitBlt`/`CopyFromScreen` screenshot does **not** correctly capture a layered/transparent window and will look black even when the overlay is rendering correctly.
- `click_log.py` uses `logging.handlers.RotatingFileHandler`, default `maxBytes=1_000_000`, `backupCount=3`, never transmitted anywhere. `CalibrationConfig.click_logging_enabled` defaults to `True`.
- Foreground window title is read via `ctypes` (`GetForegroundWindow`/`GetWindowTextLengthW`/`GetWindowTextW`) — no new dependency, matches this project's existing Windows-only scope.
- The pulse fires for every gesture action except `"none"`.
- UI strings stay in Portuguese with correct diacritics (ç, ã, á, é, í, ó, ú, and the verb "é") — do not regress this.
- Every `src/facemesh_mouse/*.py` module keeps `from __future__ import annotations` as its first import. Test files in this repo do **not** use it — match that convention in new test files.
- Run tests with `.venv\Scripts\python -m pytest tests/ -v`. The suite must end with **0 skipped** at every task boundary — a skip means a Tk-root fixture problem (see Task 1), not that something is unavailable.
- Do not modify `gestures.py`, `tracker.py`, `point_tracker.py`, `single_instance.py`, `hotkeys.py`, `gesture_panel.py`, or `config_gui.py`. Only `main.py`, `mouse_controller.py`, `engine.py`, `tray.py`, `config.py`, `calibration_panel.py`, `.gitignore`, and `README.md` change, plus two new modules and their tests.

---

### Task 1: Share one Tk root across every GUI test module

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_panels.py:1-46`

**Interfaces:**
- Produces: `root` (session-scoped) and `container` (function-scoped) pytest fixtures, discoverable by every test file under `tests/` without an import.

**Why this comes first:** Task 5 adds a new test file that needs a Tk parent widget. Each test *module* that defines its own `scope="module"` root fixture creates a **separate** Tk root the first time any of its tests run — and constructing more than one `ctk.CTk()` in one process was already proven to fail intermittently under pytest's output capture once cv2/mediapipe are loaded (this exact failure was diagnosed and fixed earlier in this project's history). Moving the fixture to `conftest.py` at `scope="session"` guarantees exactly one root for the whole test run, no matter how many files need one.

- [ ] **Step 1: Create `tests/conftest.py`**

```python
"""Shared fixtures for GUI-panel tests.

Every CustomTkinter-based test module shares ONE Tk root for the whole test
session via this fixture. Creating more than one Tk root in a process fails
intermittently under pytest's output capture once cv2/mediapipe are loaded.
Any test that needs a widget parent should depend on `container` -- never
construct a root of its own.
"""
import tkinter as tk

import pytest

ctk = pytest.importorskip("customtkinter")


@pytest.fixture(scope="session")
def root():
    from facemesh_mouse.config_gui import create_root

    try:
        window = create_root()
    except tk.TclError as exc:  # no display available
        pytest.skip(f"Tk unavailable: {exc}")
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def container(root):
    """A fresh parent widget per test, inside the one shared root."""
    frame = ctk.CTkFrame(root)
    yield frame
    frame.destroy()
```

- [ ] **Step 2: Remove the now-duplicate fixtures from `tests/test_panels.py`**

Replace lines 1-46 (everything from the top of the file through the `container` fixture's closing `frame.destroy()`):

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


@pytest.fixture
def container(root):
    """A fresh parent widget per test. The root itself is shared and never
    torn down mid-module: repeatedly creating and destroying Tk roots in one
    process fails intermittently under pytest's output capture."""
    frame = ctk.CTkFrame(root)
    yield frame
    frame.destroy()
```

with:

```python
import tkinter as tk

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


# `root` and `container` fixtures live in tests/conftest.py -- shared across
# every GUI test module in this session so only one Tk root is ever created.
```

`import pytest` is dropped here because, after this edit, nothing in `test_panels.py` uses the `pytest` name directly (its remaining tests use plain `assert`). If your editor or a later grep shows `pytest.approx` still used further down in the file, keep the `import pytest` line — check before deleting it.

- [ ] **Step 3: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — same test count as before this change (88 passed), 0 skipped.

- [ ] **Step 4: Run it four more times to confirm the intermittent-skip bug is not back**

Run: `.venv\Scripts\python -m pytest tests/ -q -rs` five times total (this one plus the four already run... run it four more times now).
Expected: `88 passed` with **no skipped** line, every single time. If any run shows a skip, stop — the fixture change introduced the exact bug it exists to prevent.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_panels.py
git commit -m "test: share one Tk root across all GUI test modules via conftest"
```

---

### Task 2: Yield cursor control to a physical mouse touch

**Files:**
- Modify: `src/facemesh_mouse/mouse_controller.py` (full rewrite)
- Modify: `src/facemesh_mouse/config.py:79-87` (`CalibrationConfig`), `:94-99` (`CALIBRATION_RANGES`), `:175-183` (`load_config`)
- Test: `tests/test_mouse_controller.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `CalibrationConfig.yield_resume_after_s: float = 3.0`, `CalibrationConfig.click_logging_enabled: bool = True` (the second field is unused until Task 6 — added here alongside the first so `config.py`'s calibration block is only edited once in this plan). `mouse_controller.YIELD_DETECT_PX: int = 2`. `MouseController.yielded: bool`, `MouseController(config, screen_size, mouse=None, clock=time.monotonic)` (new `clock` param, matching the injection pattern `GestureEngine` already uses). `MouseController.reanchor()` now also clears `yielded`.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing config tests**

Append to `tests/test_config.py`:

```python
def test_default_config_has_the_yield_and_logging_defaults():
    cal = config_mod.default_config().calibration
    assert cal.yield_resume_after_s == 3.0
    assert cal.click_logging_enabled is True


def test_yield_resume_after_s_round_trips_and_is_clamped(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.calibration.yield_resume_after_s = 5.5
    config_mod.save_config(path, original)

    assert config_mod.load_config(path).calibration.yield_resume_after_s == 5.5

    path.write_text(json.dumps({"calibration": {"yield_resume_after_s": 999}}))
    assert config_mod.load_config(path).calibration.yield_resume_after_s == 10.0


def test_click_logging_enabled_round_trips(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.calibration.click_logging_enabled = False
    config_mod.save_config(path, original)

    assert config_mod.load_config(path).calibration.click_logging_enabled is False


def test_non_bool_click_logging_value_falls_back_to_the_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"calibration": {"click_logging_enabled": "nope"}}))

    assert config_mod.load_config(path).calibration.click_logging_enabled is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: FAIL with `TypeError: CalibrationConfig.__init__() got an unexpected keyword argument 'yield_resume_after_s'`

- [ ] **Step 3: Update `CalibrationConfig`**

In `src/facemesh_mouse/config.py`, replace:

```python
@dataclass
class CalibrationConfig:
    """Cursor tuning. Defaults are tracky-mouse's shipped values; vertical
    sensitivity is twice horizontal because heads travel less vertically."""

    sensitivity_x: float = 0.025
    sensitivity_y: float = 0.05
    acceleration: float = 0.5  # 0 = linear; higher damps small movements harder
    motion_threshold_px: float = 0.0  # cursor movement below this is dropped
```

with:

```python
@dataclass
class CalibrationConfig:
    """Cursor tuning. Defaults are tracky-mouse's shipped values; vertical
    sensitivity is twice horizontal because heads travel less vertically."""

    sensitivity_x: float = 0.025
    sensitivity_y: float = 0.05
    acceleration: float = 0.5  # 0 = linear; higher damps small movements harder
    motion_threshold_px: float = 0.0  # cursor movement below this is dropped
    yield_resume_after_s: float = 3.0  # quiet period before resuming after a physical-mouse touch
    click_logging_enabled: bool = True  # record fired actions to clicks.log
```

- [ ] **Step 4: Extend `CALIBRATION_RANGES` and `load_config`**

Replace:

```python
CALIBRATION_RANGES = {
    "sensitivity_x": (0.005, 0.10),
    "sensitivity_y": (0.005, 0.10),
    "acceleration": (0.0, 1.0),
    "motion_threshold_px": (0.0, 10.0),
}
```

with:

```python
CALIBRATION_RANGES = {
    "sensitivity_x": (0.005, 0.10),
    "sensitivity_y": (0.005, 0.10),
    "acceleration": (0.0, 1.0),
    "motion_threshold_px": (0.0, 10.0),
    "yield_resume_after_s": (1.0, 10.0),
}
```

Then replace:

```python
    raw_cal = raw.get("calibration", {})
    calibration = CalibrationConfig(
        sensitivity_x=_clamped(raw_cal, "sensitivity_x", default.calibration.sensitivity_x),
        sensitivity_y=_clamped(raw_cal, "sensitivity_y", default.calibration.sensitivity_y),
        acceleration=_clamped(raw_cal, "acceleration", default.calibration.acceleration),
        motion_threshold_px=_clamped(
            raw_cal, "motion_threshold_px", default.calibration.motion_threshold_px
        ),
    )
```

with:

```python
    raw_cal = raw.get("calibration", {})
    click_logging_enabled = raw_cal.get(
        "click_logging_enabled", default.calibration.click_logging_enabled
    )
    if not isinstance(click_logging_enabled, bool):
        click_logging_enabled = default.calibration.click_logging_enabled
    calibration = CalibrationConfig(
        sensitivity_x=_clamped(raw_cal, "sensitivity_x", default.calibration.sensitivity_x),
        sensitivity_y=_clamped(raw_cal, "sensitivity_y", default.calibration.sensitivity_y),
        acceleration=_clamped(raw_cal, "acceleration", default.calibration.acceleration),
        motion_threshold_px=_clamped(
            raw_cal, "motion_threshold_px", default.calibration.motion_threshold_px
        ),
        yield_resume_after_s=_clamped(
            raw_cal, "yield_resume_after_s", default.calibration.yield_resume_after_s
        ),
        click_logging_enabled=click_logging_enabled,
    )
```

(`bool` is not stored in `CALIBRATION_RANGES`/`_clamped` because it isn't a numeric range — it's validated by `isinstance` instead.)

- [ ] **Step 5: Run the config tests**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: PASS (all tests, including the 4 new ones)

- [ ] **Step 6: Write the failing `MouseController` tests**

Update the `_config` helper near the top of `tests/test_mouse_controller.py` — replace:

```python
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
```

with:

```python
def _config(
    sensitivity_x=0.025,
    sensitivity_y=0.05,
    acceleration=0.0,
    motion_threshold_px=0.0,
    yield_resume_after_s=3.0,
):
    return AppConfig(
        calibration=CalibrationConfig(
            sensitivity_x=sensitivity_x,
            sensitivity_y=sensitivity_y,
            acceleration=acceleration,
            motion_threshold_px=motion_threshold_px,
            yield_resume_after_s=yield_resume_after_s,
        ),
        gestures={},
    )


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t
```

Then append these tests to the end of the file:

```python
def test_move_cursor_yields_when_the_cursor_diverges_from_the_last_write():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    mouse.position = (700, 500)  # simulate a physical-mouse touch
    controller.move_cursor(4.0, 0.0)

    assert controller.yielded is True
    assert mouse.position == (700, 500)  # untouched by tracked movement


def test_yielded_cursor_ignores_tracked_movement_until_the_quiet_period_elapses():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(acceleration=0.0, yield_resume_after_s=3.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    mouse.position = (700, 500)
    controller.move_cursor(4.0, 0.0)  # enters yielded at t=0
    assert controller.yielded is True

    clock.t = 2.9
    controller.move_cursor(4.0, 0.0)  # still within the quiet period
    assert controller.yielded is True
    assert mouse.position == (700, 500)

    clock.t = 3.1
    controller.move_cursor(4.0, 0.0)  # quiet period elapsed -> resumes
    assert controller.yielded is False


def test_continued_physical_movement_keeps_resetting_the_quiet_timer():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(acceleration=0.0, yield_resume_after_s=3.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    mouse.position = (700, 500)
    controller.move_cursor(0.0, 0.0)  # enters yielded at t=0

    clock.t = 2.9
    mouse.position = (750, 500)  # the user is still moving the physical mouse
    controller.move_cursor(0.0, 0.0)

    clock.t = 5.0  # 2.1s since the last movement -- well under the 3s quiet period
    controller.move_cursor(0.0, 0.0)
    assert controller.yielded is True


def test_resuming_from_yield_reanchors_with_no_jump():
    clock = FakeClock()
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(
        _config(acceleration=0.0, yield_resume_after_s=3.0), (1000, 1000), mouse=mouse, clock=clock
    )
    controller.reanchor()

    mouse.position = (700, 500)
    controller.move_cursor(0.0, 0.0)

    clock.t = 3.1
    controller.move_cursor(0.0, 0.0)

    assert mouse.position == (700, 500)  # resume must not move the cursor
    assert controller._cursor_x == 700


def test_small_cursor_drift_is_not_mistaken_for_a_physical_move():
    mouse = FakeMouse(start=(500, 500))
    controller = MouseController(_config(acceleration=0.0), (1000, 1000), mouse=mouse)
    controller.reanchor()

    mouse.position = (501, 500)  # within YIELD_DETECT_PX
    controller.move_cursor(4.0, 0.0)

    assert controller.yielded is False
```

- [ ] **Step 7: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_mouse_controller.py -v`
Expected: FAIL with `AttributeError: 'MouseController' object has no attribute 'yielded'` (or a `TypeError` on the `clock=` keyword)

- [ ] **Step 8: Rewrite `mouse_controller.py`**

Replace the entire file:

```python
"""Cursor movement math + action execution via pynput.

The acceleration curve is ported from tracky-mouse (MIT, (c) Isaiah
Odhner), https://github.com/1j01/tracky-mouse. It damps small movements
hard while leaving large ones fast, which stabilizes the cursor without an
averaging filter's latency -- each frame's output depends only on that
frame's input.

The pure math (`accelerate`, `clamp`) is separated from the pynput-driving
`MouseController` so it can be unit tested without a real display or OS
mouse.
"""
from __future__ import annotations

import math
import time
from typing import Callable

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

# OS cursor-position rounding tolerance: a divergence beyond this from the
# position this controller last wrote means something else -- the physical
# mouse -- moved the cursor.
YIELD_DETECT_PX = 2


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def accelerate(delta: float, acceleration: float) -> float:
    """Power curve: small movements shrink far more than large ones, so
    holding still is genuinely still and fine positioning is possible while
    big movements stay fast. `acceleration` of 0 is a linear pass-through."""
    return delta * (abs(delta * 5.0) ** acceleration)


class MouseController:
    def __init__(
        self,
        config: AppConfig,
        screen_size: tuple[int, int],
        mouse=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._screen_w, self._screen_h = screen_size
        self._mouse = mouse if mouse is not None else Controller()
        self._clock = clock
        self._cursor_x: float | None = None
        self._cursor_y: float | None = None
        self.yielded = False
        self._yield_started_at: float | None = None
        self._last_seen_x: float | None = None
        self._last_seen_y: float | None = None

    def update_config(self, config: AppConfig) -> None:
        self._config = config

    def reanchor(self) -> None:
        """Resyncs to the real OS cursor position, so a cursor moved by a
        physical mouse (while paused, or while yielded) is not fought."""
        cur_x, cur_y = self._mouse.position
        self._cursor_x = float(cur_x)
        self._cursor_y = float(cur_y)
        self._last_seen_x = float(cur_x)
        self._last_seen_y = float(cur_y)
        self.yielded = False
        self._yield_started_at = None

    def move_cursor(self, movement_x: float, movement_y: float) -> None:
        """Applies one frame of averaged point movement, in camera pixels."""
        if self._cursor_x is None:
            return  # not yet reanchored -- nothing to compare or move from

        cur_x, cur_y = self._mouse.position

        if self.yielded:
            self._update_yield_timer(cur_x, cur_y)
            return

        if (
            abs(cur_x - self._cursor_x) > YIELD_DETECT_PX
            or abs(cur_y - self._cursor_y) > YIELD_DETECT_PX
        ):
            # Something other than this controller moved the cursor -- the
            # physical mouse. Stop fighting it.
            self.yielded = True
            self._yield_started_at = self._clock()
            self._last_seen_x, self._last_seen_y = float(cur_x), float(cur_y)
            return

        if not (math.isfinite(movement_x) and math.isfinite(movement_y)):
            # clamp() would turn a NaN into the screen edge rather than
            # rejecting it, teleporting the cursor. Drop the frame instead.
            return

        cal = self._config.calibration
        delta_x = accelerate(movement_x * cal.sensitivity_x, cal.acceleration)
        delta_y = accelerate(movement_y * cal.sensitivity_y, cal.acceleration)

        # Threshold after the curve, so its unit is honestly "screen pixels
        # of cursor movement" rather than pixels before a curve is applied.
        if abs(delta_x * self._screen_w) < cal.motion_threshold_px:
            delta_x = 0.0
        if abs(delta_y * self._screen_h) < cal.motion_threshold_px:
            delta_y = 0.0

        # The tracked frame is already mirrored by FaceTracker.process, so
        # camera x matches screen x: the user's right is +x in both. (Upstream
        # tracky-mouse subtracts here because it tracks an unmirrored frame.)
        self._cursor_x = clamp(
            self._cursor_x + delta_x * self._screen_w, 0, self._screen_w - 1
        )
        self._cursor_y = clamp(
            self._cursor_y + delta_y * self._screen_h, 0, self._screen_h - 1
        )
        self._mouse.position = (int(self._cursor_x), int(self._cursor_y))

    def _update_yield_timer(self, cur_x: int, cur_y: int) -> None:
        if (
            abs(cur_x - self._last_seen_x) > YIELD_DETECT_PX
            or abs(cur_y - self._last_seen_y) > YIELD_DETECT_PX
        ):
            # Still moving -- keep pushing the resume deadline out.
            self._yield_started_at = self._clock()
        self._last_seen_x, self._last_seen_y = float(cur_x), float(cur_y)

        quiet_for = self._clock() - self._yield_started_at
        if quiet_for >= self._config.calibration.yield_resume_after_s:
            self.reanchor()

    def fire_action(self, gesture_name: str) -> None:
        action = self._config.gestures[gesture_name].action
        _ACTIONS[action](self._mouse)
```

- [ ] **Step 9: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_mouse_controller.py -v`
Expected: PASS (all tests, existing and new)

- [ ] **Step 10: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 97 passed (88 + 4 config + 5 mouse_controller), 0 skipped

- [ ] **Step 11: Commit**

```bash
git add src/facemesh_mouse/mouse_controller.py src/facemesh_mouse/config.py tests/test_mouse_controller.py tests/test_config.py
git commit -m "feat(mouse): yield cursor control to a physical mouse touch, auto-resume"
```

---

### Task 3: Tray indicator for the yielded state

**Files:**
- Modify: `src/facemesh_mouse/tray.py` (full rewrite)
- Modify: `src/facemesh_mouse/engine.py:87-89` (add a property)
- Modify: `src/facemesh_mouse/main.py:104-106` (rename and extend the poll function), `:91` (call site)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `MouseController.yielded` (Task 2).
- Produces: `Engine.mouse_controller` (property, `MouseController | None`). `TrayIcon.set_yielded(yielded: bool) -> None`.

No automated test for `tray.py` itself — it's real-system-tray code, manual-checklist only, consistent with the rest of this file (unchanged convention from earlier plans).

- [ ] **Step 1: Add the `mouse_controller` property to `Engine`**

In `src/facemesh_mouse/engine.py`, replace:

```python
    def open_camera(self) -> bool:
        self._camera = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        return self._camera.isOpened()
```

with:

```python
    @property
    def mouse_controller(self) -> MouseController | None:
        """Exposes the controller so callers outside the engine thread (the
        tray-status poll, in main.py) can read its `yielded` state. `None`
        until `start()` has run."""
        return self._mouse_controller

    def open_camera(self) -> bool:
        self._camera = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        return self._camera.isOpened()
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_engine.py`:

```python
def test_mouse_controller_property_exposes_the_controller_after_start():
    engine = Engine(default_config())
    assert engine.mouse_controller is None

    engine._mouse_controller = MagicMock()
    assert engine.mouse_controller is engine._mouse_controller
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_engine.py -v`
Expected: FAIL with `AttributeError: 'Engine' object has no attribute 'mouse_controller'` if Step 1 hasn't landed yet in your working copy — but since you just did Step 1, this should already PASS. Run it anyway to confirm.

Expected (actual): PASS (all tests, including the new one)

- [ ] **Step 4: Rewrite `tray.py`**

Replace the entire file:

```python
"""System tray icon: Pause/Resume, Open Config, Quit.

Icon color reflects one state, chosen by precedence (highest first): paused
overrides everything else the user might also be seeing (a face, a physical
mouse) since it's the state they explicitly asked for; yielded overrides
no-face and running.
"""
from __future__ import annotations

import threading
from typing import Callable

import pystray
from PIL import Image, ImageDraw


def _make_icon_image(color: str) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, size - 8, size - 8), fill=color)
    return img


_ICON_RUNNING = _make_icon_image("#2ecc71")
_ICON_PAUSED = _make_icon_image("#f1c40f")
_ICON_NO_FACE = _make_icon_image("#e67e22")
_ICON_YIELDED = _make_icon_image("#3498db")


class TrayIcon:
    def __init__(
        self,
        on_toggle_pause: Callable[[], bool],
        on_open_config: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_toggle_pause = on_toggle_pause
        self._on_open_config = on_open_config
        self._on_quit = on_quit
        self._paused = False
        self._no_face = False
        self._yielded = False
        self._icon = pystray.Icon(
            "facemesh_mouse",
            _ICON_RUNNING,
            "FaceMesh Mouse",
            menu=pystray.Menu(
                pystray.MenuItem(self._pause_label, self._toggle_pause),
                pystray.MenuItem("Reabrir Config", self._open_config, default=True),
                pystray.MenuItem("Sair", self._quit),
            ),
        )

    def _pause_label(self, _item) -> str:
        return "Retomar" if self._paused else "Pausar"

    def _toggle_pause(self, _icon=None, _item=None) -> None:
        self._paused = self._on_toggle_pause()
        self._refresh()
        self._icon.update_menu()

    def toggle_pause(self) -> None:
        """Public entry point for external callers (e.g. global hotkeys)."""
        self._toggle_pause()

    def _open_config(self, _icon=None, _item=None) -> None:
        self._on_open_config()

    def _quit(self, _icon=None, _item=None) -> None:
        self._on_quit()
        self._icon.stop()

    def set_no_face(self, no_face: bool) -> None:
        self._no_face = no_face
        self._refresh()

    def set_yielded(self, yielded: bool) -> None:
        """Called when cursor control is yielded to a physical mouse touch
        (see `MouseController.yielded`)."""
        self._yielded = yielded
        self._refresh()

    def _refresh(self) -> None:
        if self._paused:
            self._icon.icon = _ICON_PAUSED
        elif self._yielded:
            self._icon.icon = _ICON_YIELDED
        elif self._no_face:
            self._icon.icon = _ICON_NO_FACE
        else:
            self._icon.icon = _ICON_RUNNING

    def run_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._icon.stop()
```

- [ ] **Step 5: Rename and extend the poll function in `main.py`**

Replace:

```python
    _poll_no_face(root, engine, tray)
```

with:

```python
    _poll_status(root, engine, tray)
```

Replace:

```python
def _poll_no_face(root: tk.Tk, engine: Engine, tray: TrayIcon) -> None:
    tray.set_no_face(engine.no_face.is_set())
    root.after(500, _poll_no_face, root, engine, tray)
```

with:

```python
def _poll_status(root: tk.Tk, engine: Engine, tray: TrayIcon) -> None:
    tray.set_no_face(engine.no_face.is_set())
    mouse_controller = engine.mouse_controller
    tray.set_yielded(mouse_controller.yielded if mouse_controller is not None else False)
    root.after(500, _poll_status, root, engine, tray)
```

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 98 passed, 0 skipped

- [ ] **Step 7: Syntax-check**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/*.py`
Expected: clean

- [ ] **Step 8: Commit**

```bash
git add src/facemesh_mouse/tray.py src/facemesh_mouse/engine.py src/facemesh_mouse/main.py tests/test_engine.py
git commit -m "feat(tray): blue icon while cursor control is yielded to the physical mouse"
```

---

### Task 4: Click log — rotating local record of every fired action

**Files:**
- Create: `src/facemesh_mouse/click_log.py`
- Test: `tests/test_click_log.py`

**Interfaces:**
- Produces: `click_log.enable(path=LOG_PATH, max_bytes=1_000_000, backup_count=3) -> None`, `click_log.disable() -> None`, `click_log.record(gesture_name: str, action: str, position: tuple[int, int], window_title_fn: Callable[[], str] = _foreground_window_title) -> None`, `click_log.LOG_PATH: str = "clicks.log"`.
- Consumes: nothing from other tasks. Nothing calls this module until Task 6.

This task is standalone: no Tk dependency, no `MouseController` dependency.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_click_log.py`:

```python
import pytest

from facemesh_mouse import click_log


@pytest.fixture(autouse=True)
def _reset_logger():
    """The module-level logger is process-global state shared by every
    test in this file -- reset it before and after each test so tests
    can't see each other's handlers."""
    click_log.disable()
    yield
    click_log.disable()


def test_record_without_enable_writes_nothing(tmp_path):
    path = tmp_path / "clicks.log"

    click_log.record("blink_a", "left_click", (0, 0))

    assert not path.exists()


def test_record_writes_one_parseable_line(tmp_path):
    path = tmp_path / "clicks.log"
    click_log.enable(path)

    click_log.record("blink_a", "left_click", (842, 511), window_title_fn=lambda: "Notepad")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "blink_a" in lines[0]
    assert "left_click" in lines[0]
    assert "(842, 511)" in lines[0]
    assert '"Notepad"' in lines[0]


def test_enable_twice_does_not_duplicate_handlers(tmp_path):
    path = tmp_path / "clicks.log"
    click_log.enable(path)
    click_log.enable(path)

    click_log.record("blink_a", "left_click", (0, 0), window_title_fn=lambda: "X")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # would be 2 if the handler got attached twice


def test_disable_stops_further_writes(tmp_path):
    path = tmp_path / "clicks.log"
    click_log.enable(path)
    click_log.record("blink_a", "left_click", (0, 0), window_title_fn=lambda: "X")
    click_log.disable()

    click_log.record("blink_a", "left_click", (0, 0), window_title_fn=lambda: "X")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # the record() after disable() must not append


def test_rotation_creates_a_backup_past_max_bytes(tmp_path):
    path = tmp_path / "clicks.log"
    click_log.enable(path, max_bytes=500, backup_count=2)

    for i in range(50):
        click_log.record("blink_a", "left_click", (i, i), window_title_fn=lambda: "x" * 40)

    assert (tmp_path / "clicks.log.1").exists()


def test_foreground_window_title_does_not_raise():
    title = click_log._foreground_window_title()

    assert isinstance(title, str)
    assert title != ""
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_click_log.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.click_log'`

- [ ] **Step 3: Create `click_log.py`**

```python
"""Rotating local log of every gesture-fired mouse action.

Never sent anywhere -- a plain text file in the app directory, capped by
rotation so it can't grow without bound. Attaching a handler is opt-in via
`enable()`; until that's called, `record()` is a no-op that never touches
the filesystem, so disabling logging in the GUI costs nothing per click.
"""
from __future__ import annotations

import ctypes
import logging
import logging.handlers
from pathlib import Path
from typing import Callable

LOG_PATH = "clicks.log"

_logger = logging.getLogger("facemesh_mouse.clicks")
_logger.setLevel(logging.INFO)
_logger.propagate = False


def enable(
    path: str | Path = LOG_PATH,
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
) -> None:
    """Attaches the rotating file handler. Safe to call more than once --
    a second call is a no-op, so it never doubles up handlers."""
    if _logger.handlers:
        return
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(handler)


def disable() -> None:
    for handler in list(_logger.handlers):
        _logger.removeHandler(handler)
        handler.close()


def _foreground_window_title() -> str:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value or "?"
    except Exception:
        # A missing/renamed window mid-transition must never break logging
        # or crash the caller -- "?" is a fine record for a rare edge case.
        return "?"


def record(
    gesture_name: str,
    action: str,
    position: tuple[int, int],
    window_title_fn: Callable[[], str] = _foreground_window_title,
) -> None:
    if not _logger.handlers:
        return
    title = window_title_fn() or "?"
    _logger.info(
        '%s %s (%d, %d) "%s"', gesture_name, action, position[0], position[1], title
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_click_log.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 104 passed, 0 skipped

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/click_log.py tests/test_click_log.py
git commit -m "feat(log): rotating local record of every gesture-fired action"
```

---

### Task 5: Click feedback — click-through visual pulse at the cursor

**Files:**
- Create: `src/facemesh_mouse/click_feedback.py`
- Test: `tests/test_click_feedback.py`

**Interfaces:**
- Produces: `click_feedback.show_pulse(parent: tk.Misc, x: int, y: int) -> tk.Toplevel | None`, `click_feedback.GWL_EXSTYLE`, `click_feedback.WS_EX_TRANSPARENT`, `click_feedback.WS_EX_LAYERED` (exposed as module constants so tests can check style bits).
- Consumes: `tests/conftest.py`'s `container` fixture (Task 1). Nothing calls `show_pulse` from application code until Task 6.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_click_feedback.py`:

```python
import ctypes

import pytest

from facemesh_mouse import click_feedback


def test_show_pulse_creates_a_click_through_topmost_window(container):
    window = click_feedback.show_pulse(container, 100, 100)

    assert window is not None
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(hwnd, click_feedback.GWL_EXSTYLE)

    assert styles & click_feedback.WS_EX_TRANSPARENT
    assert styles & click_feedback.WS_EX_LAYERED

    window.destroy()


def test_show_pulse_positions_the_window_around_the_given_point(container):
    window = click_feedback.show_pulse(container, 500, 300)

    assert window is not None
    size = window.winfo_width()
    assert window.winfo_x() == pytest.approx(500 - size // 2, abs=2)
    assert window.winfo_y() == pytest.approx(300 - size // 2, abs=2)

    window.destroy()


def test_show_pulse_survives_a_broken_render(monkeypatch, container):
    """A missing pulse must never crash tracking -- verify the guard by
    forcing the internal implementation to raise."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated overlay failure")

    monkeypatch.setattr(click_feedback, "_show_pulse", _boom)

    result = click_feedback.show_pulse(container, 0, 0)

    assert result is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_click_feedback.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.click_feedback'`

- [ ] **Step 3: Create `click_feedback.py`**

```python
"""Click-through visual pulse shown at the cursor when a gesture fires an
action.

A borderless, always-on-top ring that expands and fades over ~300ms, then
destroys itself. Click-through is essential: without it the overlay window
would intercept the very next click, which would be actively harmful for a
tool whose whole purpose is clicking.

The click-through recipe (GetParent(winfo_id()) + WS_EX_TRANSPARENT) was
verified against this project's actual Tcl/Tk build: winfo_id() returns a
Tk-internal child window, and the real top-level HWND Windows composites --
the one that must carry the extended styles -- is its parent. Verifying the
visual result requires PrintWindow with PW_RENDERFULLCONTENT; a plain
BitBlt/CopyFromScreen capture does not correctly show a layered window.
"""
from __future__ import annotations

import ctypes
import tkinter as tk

_DURATION_MS = 300
_STEPS = 10
_START_RADIUS = 6
_END_RADIUS = 28
_RING_COLOR = "#4da3ff"

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080


def _make_click_through(window: tk.Toplevel) -> None:
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE, styles | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
    )


def show_pulse(parent: tk.Misc, x: int, y: int) -> tk.Toplevel | None:
    """Shows one expanding ring centered on (x, y), in screen coordinates.
    Returns the Toplevel (mainly so tests can inspect it) -- callers driving
    the real app can ignore the return value."""
    try:
        return _show_pulse(parent, x, y)
    except Exception as exc:  # noqa: BLE001 - a missing pulse must never crash tracking
        print(f"facemesh-mouse: click pulse failed ({exc!r})")
        return None


def _show_pulse(parent: tk.Misc, x: int, y: int) -> tk.Toplevel:
    size = _END_RADIUS * 2 + 4
    window = tk.Toplevel(parent)
    window.overrideredirect(True)
    window.attributes("-topmost", True)
    window.attributes("-transparentcolor", "black")
    window.configure(bg="black")
    window.geometry(f"{size}x{size}+{x - size // 2}+{y - size // 2}")

    canvas = tk.Canvas(window, width=size, height=size, bg="black", highlightthickness=0)
    canvas.pack()

    window.update_idletasks()
    _make_click_through(window)

    center = size / 2

    def step(index: int) -> None:
        if not window.winfo_exists():
            return
        canvas.delete("all")
        if index > _STEPS:
            window.destroy()
            return
        progress = index / _STEPS
        radius = _START_RADIUS + (_END_RADIUS - _START_RADIUS) * progress
        canvas.create_oval(
            center - radius, center - radius, center + radius, center + radius,
            outline=_RING_COLOR, width=3,
        )
        window.after(_DURATION_MS // _STEPS, step, index + 1)

    step(0)
    return window
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_click_feedback.py -v`
Expected: PASS (3 tests). If `test_show_pulse_positions_the_window_around_the_given_point` is flaky about exact pixel position, allow it — the `abs=2` tolerance already accounts for `winfo_x`/`winfo_y` rounding.

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 107 passed, 0 skipped

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/click_feedback.py tests/test_click_feedback.py
git commit -m "feat(gui): click-through visual pulse at the cursor on every gesture action"
```

---

### Task 6: Wire it all together — on_action callback, GUI controls, docs

**Files:**
- Modify: `src/facemesh_mouse/mouse_controller.py` (`fire_action` + `__init__`)
- Modify: `src/facemesh_mouse/engine.py` (`__init__` + `start`)
- Modify: `src/facemesh_mouse/main.py` (full rewrite)
- Modify: `src/facemesh_mouse/calibration_panel.py`
- Modify: `tests/test_mouse_controller.py`, `tests/test_panels.py`
- Modify: `.gitignore`, `README.md`

**Interfaces:**
- Consumes: `click_feedback.show_pulse` (Task 5), `click_log.enable`/`disable`/`record` (Task 4), `MouseController.yielded` and the `reanchor()`/`move_cursor()` shapes (Task 2, unchanged by this task), `Engine.mouse_controller` (Task 3, unchanged by this task).
- Produces: `MouseController(..., on_action: Callable[[str, str, tuple[int, int]], None] | None = None)`. `Engine(config, camera_index=0, on_action=None)`.

- [ ] **Step 1: Write the failing `fire_action` tests**

Append to `tests/test_mouse_controller.py`:

```python
from facemesh_mouse.config import GestureConfig


def test_fire_action_invokes_on_action_callback():
    mouse = FakeMouse()
    calls = []
    config = AppConfig(
        calibration=CalibrationConfig(),
        gestures={"blink_a": GestureConfig(action="left_click")},
    )
    controller = MouseController(
        config, (1000, 1000), mouse=mouse, on_action=lambda *args: calls.append(args)
    )

    controller.fire_action("blink_a")

    assert calls == [("blink_a", "left_click", mouse.position)]


def test_fire_action_does_not_invoke_on_action_for_none():
    mouse = FakeMouse()
    calls = []
    config = AppConfig(
        calibration=CalibrationConfig(),
        gestures={"blink_a": GestureConfig(action="none")},
    )
    controller = MouseController(
        config, (1000, 1000), mouse=mouse, on_action=lambda *args: calls.append(args)
    )

    controller.fire_action("blink_a")

    assert calls == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_mouse_controller.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'on_action'`

- [ ] **Step 3: Add `on_action` to `MouseController`**

In `src/facemesh_mouse/mouse_controller.py`, replace:

```python
    def __init__(
        self,
        config: AppConfig,
        screen_size: tuple[int, int],
        mouse=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._screen_w, self._screen_h = screen_size
        self._mouse = mouse if mouse is not None else Controller()
        self._clock = clock
        self._cursor_x: float | None = None
```

with:

```python
    def __init__(
        self,
        config: AppConfig,
        screen_size: tuple[int, int],
        mouse=None,
        clock: Callable[[], float] = time.monotonic,
        on_action: Callable[[str, str, tuple[int, int]], None] | None = None,
    ) -> None:
        self._config = config
        self._screen_w, self._screen_h = screen_size
        self._mouse = mouse if mouse is not None else Controller()
        self._clock = clock
        self._on_action = on_action
        self._cursor_x: float | None = None
```

Then replace:

```python
    def fire_action(self, gesture_name: str) -> None:
        action = self._config.gestures[gesture_name].action
        _ACTIONS[action](self._mouse)
```

with:

```python
    def fire_action(self, gesture_name: str) -> None:
        action = self._config.gestures[gesture_name].action
        if action != "none" and self._on_action is not None:
            self._on_action(gesture_name, action, self._mouse.position)
        _ACTIONS[action](self._mouse)
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_mouse_controller.py -v`
Expected: PASS (all tests, including the 2 new ones)

- [ ] **Step 5: Wire `Engine` to pass `on_action` through**

In `src/facemesh_mouse/engine.py`, add to the imports:

```python
from typing import Callable
```

Replace:

```python
    def __init__(self, config: AppConfig, camera_index: int = 0) -> None:
        self.state = SharedState()
        self.control_enabled = threading.Event()  # set = GUI hidden, control live
        self.paused = threading.Event()  # set = user paused via tray/hotkey
        self.no_face = threading.Event()

        self._config = config
        self._stop = threading.Event()
```

with:

```python
    def __init__(
        self,
        config: AppConfig,
        camera_index: int = 0,
        on_action: Callable[[str, str, tuple[int, int]], None] | None = None,
    ) -> None:
        self.state = SharedState()
        self.control_enabled = threading.Event()  # set = GUI hidden, control live
        self.paused = threading.Event()  # set = user paused via tray/hotkey
        self.no_face = threading.Event()

        self._config = config
        self._on_action = on_action
        self._stop = threading.Event()
```

Then replace:

```python
    def start(self, screen_size: tuple[int, int]) -> None:
        self._tracker = FaceTracker()
        self._mouse_controller = MouseController(self._config, screen_size)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
```

with:

```python
    def start(self, screen_size: tuple[int, int]) -> None:
        self._tracker = FaceTracker()
        self._mouse_controller = MouseController(
            self._config, screen_size, on_action=self._on_action
        )
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
```

- [ ] **Step 6: Add the sliders and switch to `calibration_panel.py`**

In `src/facemesh_mouse/calibration_panel.py`, replace the `SLIDER_SPECS` dict's closing brace context — add a new entry after `"motion_threshold_px"`:

```python
    "motion_threshold_px": (
        "Limiar de movimento",
        0.0,
        10.0,
        "Ignora movimentos menores que isso, em pixels. Ajuda o cursor a "
        "parar completamente.",
    ),
}
```

with:

```python
    "motion_threshold_px": (
        "Limiar de movimento",
        0.0,
        10.0,
        "Ignora movimentos menores que isso, em pixels. Ajuda o cursor a "
        "parar completamente.",
    ),
    "yield_resume_after_s": (
        "Retomar após usar o mouse físico",
        1.0,
        10.0,
        "Depois de tocar no mouse ou trackpad, esse é o tempo parado que o "
        "app espera antes de a cabeça voltar a controlar o cursor.",
    ),
}
```

Replace the `_VALUE_FORMATS` dict:

```python
_VALUE_FORMATS = {
    "sensitivity_x": lambda value: f"{value:.3f}",
    "sensitivity_y": lambda value: f"{value:.3f}",
    "acceleration": lambda value: f"{value:.2f}",
    "motion_threshold_px": lambda value: f"{value:.1f} px",
}
```

with:

```python
_VALUE_FORMATS = {
    "sensitivity_x": lambda value: f"{value:.3f}",
    "sensitivity_y": lambda value: f"{value:.3f}",
    "acceleration": lambda value: f"{value:.2f}",
    "motion_threshold_px": lambda value: f"{value:.1f} px",
    "yield_resume_after_s": lambda value: f"{value:.1f} s",
}
```

Replace the `_build` method:

```python
    def _build(self) -> None:
        self.frame.grid_columnconfigure(0, weight=1)
        row = 0
        for field, (label, low, high, description) in SLIDER_SPECS.items():
            row = self._build_row(row, field, label, low, high, description)
```

with:

```python
    def _build(self) -> None:
        self.frame.grid_columnconfigure(0, weight=1)
        row = 0
        for field, (label, low, high, description) in SLIDER_SPECS.items():
            row = self._build_row(row, field, label, low, high, description)
        self._build_click_logging_switch(row)

    def _build_click_logging_switch(self, row: int) -> None:
        self._click_logging_var = ctk.BooleanVar(
            value=self._config.calibration.click_logging_enabled
        )
        ctk.CTkSwitch(
            self.frame,
            text="Registrar cliques em clicks.log",
            variable=self._click_logging_var,
        ).grid(row=row, column=0, sticky="w", pady=(14, 2))
        row += 1
        ctk.CTkLabel(
            self.frame,
            text="Guarda um histórico local do que foi clicado: gesto, ação, "
            "posição e a janela em foco. Nunca é enviado para lugar nenhum.",
            justify="left",
            wraplength=380,
            anchor="w",
            text_color="gray70",
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
```

Replace `apply_to_config`:

```python
    def apply_to_config(self) -> None:
        cal = self._config.calibration
        cal.sensitivity_x = round(self.sliders["sensitivity_x"].get(), 4)
        cal.sensitivity_y = round(self.sliders["sensitivity_y"].get(), 4)
        cal.acceleration = round(self.sliders["acceleration"].get(), 2)
        cal.motion_threshold_px = round(self.sliders["motion_threshold_px"].get(), 1)
```

with:

```python
    def apply_to_config(self) -> None:
        cal = self._config.calibration
        cal.sensitivity_x = round(self.sliders["sensitivity_x"].get(), 4)
        cal.sensitivity_y = round(self.sliders["sensitivity_y"].get(), 4)
        cal.acceleration = round(self.sliders["acceleration"].get(), 2)
        cal.motion_threshold_px = round(self.sliders["motion_threshold_px"].get(), 1)
        cal.yield_resume_after_s = round(self.sliders["yield_resume_after_s"].get(), 1)
        cal.click_logging_enabled = bool(self._click_logging_var.get())
```

- [ ] **Step 7: Update the panel tests**

In `tests/test_panels.py`, replace:

```python
def test_calibration_panel_has_a_slider_per_tuning_field(container):
    panel = CalibrationPanel(container, default_config())

    assert set(panel.sliders) == {
        "sensitivity_x",
        "sensitivity_y",
        "acceleration",
        "motion_threshold_px",
    }
```

with:

```python
def test_calibration_panel_has_a_slider_per_tuning_field(container):
    panel = CalibrationPanel(container, default_config())

    assert set(panel.sliders) == {
        "sensitivity_x",
        "sensitivity_y",
        "acceleration",
        "motion_threshold_px",
        "yield_resume_after_s",
    }


def test_click_logging_switch_writes_into_the_config(container):
    config = default_config()
    panel = CalibrationPanel(container, config)

    panel._click_logging_var.set(False)
    panel.apply_to_config()

    assert config.calibration.click_logging_enabled is False


def test_click_logging_switch_starts_from_the_configs_value(container):
    config = default_config()
    config.calibration.click_logging_enabled = False

    panel = CalibrationPanel(container, config)

    assert panel._click_logging_var.get() is False
```

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 111 passed, 0 skipped

- [ ] **Step 9: Wire `main.py`**

Replace the entire file:

```python
"""Entry point: wires engine, config GUI, tray icon, and hotkeys together."""
from __future__ import annotations

import sys
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

from . import click_feedback
from . import click_log
from . import config as config_mod
from . import single_instance
from .config_gui import ConfigWindow, create_root
from .engine import Engine
from .hotkeys import HotkeyListener
from .tray import TrayIcon

CONFIG_PATH = "config.json"


def _sync_click_logging(config) -> None:
    if config.calibration.click_logging_enabled:
        click_log.enable()
    else:
        click_log.disable()


def main() -> None:
    _config_window_opener = None

    def _on_singleton_signal() -> None:
        if _config_window_opener is not None:
            _config_window_opener()

    singleton_socket = single_instance.acquire_or_signal(on_signal=_on_singleton_signal)
    if singleton_socket is None:
        sys.exit(0)

    app_config = config_mod.load_config(CONFIG_PATH)
    _sync_click_logging(app_config)

    def _on_action(gesture_name: str, action: str, position: tuple[int, int]) -> None:
        root.after(0, click_feedback.show_pulse, root, position[0], position[1])
        click_log.record(gesture_name, action, position)

    engine = Engine(app_config, on_action=_on_action)

    if not engine.open_camera():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "FaceMesh Mouse",
            "Nao foi possivel acessar a webcam. Verifique se ela esta "
            "conectada e se a permissao de camera do Windows esta ativa.",
        )
        sys.exit(1)

    root = create_root()
    screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
    engine.start(screen_size)

    config_window = ConfigWindow(
        root,
        engine,
        app_config,
        CONFIG_PATH,
        on_start=_make_on_start(engine),
    )

    if Path(CONFIG_PATH).exists():
        engine.control_enabled.set()
        root.withdraw()

    def toggle_pause() -> bool:
        if engine.paused.is_set():
            engine.paused.clear()
        else:
            engine.paused.set()
        return engine.paused.is_set()

    def open_config() -> None:
        engine.control_enabled.clear()
        root.after(0, config_window.show)

    _config_window_opener = open_config

    def quit_app() -> None:
        engine.stop()
        hotkeys.stop()
        root.after(0, root.quit)

    tray = TrayIcon(
        on_toggle_pause=toggle_pause,
        on_open_config=open_config,
        on_quit=quit_app,
    )
    tray.run_in_thread()

    hotkeys = HotkeyListener(
        on_toggle_pause=tray.toggle_pause,
        on_open_config=open_config,
    )
    hotkeys.start()

    _poll_status(root, engine, tray)

    root.mainloop()


def _make_on_start(engine: Engine):
    def on_start(new_config) -> None:
        engine.update_config(new_config)
        _sync_click_logging(new_config)
        engine.control_enabled.set()

    return on_start


def _poll_status(root: tk.Tk, engine: Engine, tray: TrayIcon) -> None:
    tray.set_no_face(engine.no_face.is_set())
    mouse_controller = engine.mouse_controller
    tray.set_yielded(mouse_controller.yielded if mouse_controller is not None else False)
    root.after(500, _poll_status, root, engine, tray)


if __name__ == "__main__":
    main()
```

Note on the `root` closure: `_on_action` references `root`, which is not assigned until later in `main()`'s body (or, on the camera-failure path, assigned earlier and the process exits before `_on_action` could ever be called). This is the same pattern `_config_window_opener`/`_on_singleton_signal` already use in this file — Python resolves a closure's free variables at call time, not at definition time, and `_on_action` is only ever actually invoked well after `root = create_root()` has run (a gesture can't fire before `engine.start()` does).

- [ ] **Step 10: Update `.gitignore`**

Add one line:

```
clicks.log*
```

- [ ] **Step 11: Update `README.md`**

Replace the doc-links paragraph:

```markdown
Ver [docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md](docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md)
(design original, com os cinco gestos v1 e sem `hold_ms`),
[docs/superpowers/specs/2026-08-07-gesture-expansion-modern-ui-design.md](docs/superpowers/specs/2026-08-07-gesture-expansion-modern-ui-design.md)
(nove gestos, tempo de espera e a UI atual em abas) e
[docs/superpowers/specs/2026-08-07-optical-flow-tracking-design.md](docs/superpowers/specs/2026-08-07-optical-flow-tracking-design.md)
(cursor relativo por optical flow, sliders de sensibilidade/aceleração no
lugar da calibração de quatro pontos) para o design completo.
```

with:

```markdown
Ver [docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md](docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md)
(design original, com os cinco gestos v1 e sem `hold_ms`),
[docs/superpowers/specs/2026-08-07-gesture-expansion-modern-ui-design.md](docs/superpowers/specs/2026-08-07-gesture-expansion-modern-ui-design.md)
(nove gestos, tempo de espera e a UI atual em abas),
[docs/superpowers/specs/2026-08-07-optical-flow-tracking-design.md](docs/superpowers/specs/2026-08-07-optical-flow-tracking-design.md)
(cursor relativo por optical flow, sliders de sensibilidade/aceleração no
lugar da calibração de quatro pontos) e
[docs/superpowers/specs/2026-08-07-mouse-yield-and-click-feedback-design.md](docs/superpowers/specs/2026-08-07-mouse-yield-and-click-feedback-design.md)
(ceder controle ao mouse físico, pulso visual de clique e log local) para o
design completo.
```

Replace:

```markdown
O cursor se move de forma relativa à cabeça, como um mouse físico: `Ctrl+Alt+P`
pausa e congela o cursor a qualquer momento — use pra "levantar o mouse",
reposicionar a cabeça numa posição mais confortável, e retomar exatamente de
onde parou, sem pular.

Ícone na bandeja: Pausar/Retomar, Reabrir Config, Sair. Clique com o botão
esquerdo no ícone também reabre a config direto; botão direito mostra o
menu completo.
Atalhos globais: `Ctrl+Alt+P` pausa/retoma, `Ctrl+Alt+O` reabre a config.

Config salvo em `config.json` na raiz do projeto (ignorado pelo git).
```

with:

```markdown
O cursor se move de forma relativa à cabeça, como um mouse físico: `Ctrl+Alt+P`
pausa e congela o cursor a qualquer momento — use pra "levantar o mouse",
reposicionar a cabeça numa posição mais confortável, e retomar exatamente de
onde parou, sem pular.

Se você mexer no mouse físico ou no trackpad enquanto o controle pela cabeça
está ativo, o app cede o controle na hora: o cursor obedece o mouse físico e
a cabeça é ignorada até você parar de mexer por alguns segundos (padrão 3s,
ajustável em Movimento). O ícone da bandeja fica azul enquanto isso.

Ícone na bandeja: Pausar/Retomar, Reabrir Config, Sair. Clique com o botão
esquerdo no ícone também reabre a config direto; botão direito mostra o
menu completo.
Atalhos globais: `Ctrl+Alt+P` pausa/retoma, `Ctrl+Alt+O` reabre a config.

Cada clique disparado por gesto mostra um pulso azul na posição do cursor,
pra confirmar visualmente que o clique aconteceu — útil porque piscar ou
levantar a sobrancelha não tem o retorno tátil de um clique físico.

Todo clique também fica registrado em `clicks.log` (data, gesto, ação,
posição e a janela em foco), rotacionado automaticamente pra não crescer
sem limite; nunca é enviado pra lugar nenhum, e pode ser desligado na aba
Movimento.

Config salvo em `config.json` e histórico de cliques em `clicks.log`,
ambos na raiz do projeto (ignorados pelo git).
```

Replace:

```markdown
Cobre a lógica pura (motor de gestos, poda de pontos e curva de aceleração,
load/save de config) sem precisar de câmera real. Câmera, mouse, bandeja e
atalhos exigem checklist manual (ver spec).
```

with:

```markdown
Cobre a lógica pura (motor de gestos, poda de pontos e curva de aceleração,
cessão de controle ao mouse físico, log de cliques, load/save de config)
sem precisar de câmera real. Câmera, bandeja, atalhos e a aparência visual
do pulso exigem checklist manual (ver spec).
```

- [ ] **Step 12: Run the full suite one more time**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS — 111 passed, 0 skipped (unaffected by the `.gitignore`/`README.md`/`main.py` edits, confirms nothing broke)

- [ ] **Step 13: Syntax-check every module**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/*.py`
Expected: clean

- [ ] **Step 14: Diacritics regression check**

Run: `grep -nE "\b(cabeca|gravacao|voce|nao|maximo|direcao|aceleracao|acao|posicao)\b" src/facemesh_mouse/*.py`
Expected: no output

- [ ] **Step 15: Manual verification checklist**

Requires a real webcam. Run `.venv\Scripts\python run.py` (delete `config.json` first if you want to reach the wizard, or press `Ctrl+Alt+O` after launch):

1. Start tracking, then touch your physical mouse/trackpad — the cursor stops following your head and follows the physical device instead. Tray icon turns blue.
2. Keep moving the physical mouse for a while — the tray icon stays blue the whole time.
3. Stop touching it and wait past the configured quiet period (default 3s) — the cursor resumes following your head from exactly where the physical mouse left it, no jump. Tray icon returns to green (or orange if no face, or yellow if paused).
4. Adjust "Retomar após usar o mouse físico" in the Movimento tab, click Iniciar, and confirm the new delay is honored.
5. Trigger a mapped gesture (e.g. a blink mapped to a click) — see a blue ring pulse at the cursor position, and confirm the click still actually landed (the pulse doesn't block it).
6. Open `clicks.log` in the project root after a short session — one readable line per action fired, with a timestamp, gesture, action, position, and window title.
7. Toggle "Registrar cliques em clicks.log" off in Movimento, click Iniciar, trigger a few more gestures, and confirm no new lines were appended.

- [ ] **Step 16: Commit**

```bash
git add src/facemesh_mouse tests/test_mouse_controller.py tests/test_panels.py .gitignore README.md
git commit -m "feat: wire click pulse and click log to gesture-fired actions"
```

---

## Self-Review Notes

- **Spec coverage:** yield detection/state machine/auto-resume → Task 2; tray indicator → Task 3; click-through pulse → Task 5, wired in Task 6; rotating click log → Task 4, wired in Task 6; GUI controls for both new settings → Task 6; error handling (missing window title → `"?"`, overlay construction failure caught) → Tasks 4-5; every scenario in the spec's Testing section → Tasks 2-6; manual checklist → Task 6 Step 15.
- **Placeholder scan:** no TBD/TODO; every step carries literal code or an exact command.
- **Type/name consistency checked:** `MouseController.reanchor()`/`move_cursor(x, y)` signatures are unchanged from Task 2 onward (Task 6 only adds `on_action`, a new constructor kwarg, not a signature change to existing methods) — the existing `Engine._drive_control` call sites (`reanchor()`, `move_cursor(*movement)`) need no edits anywhere in this plan. `on_action`'s `(gesture_name: str, action: str, position: tuple[int, int])` shape matches identically across `MouseController.fire_action`'s call, `Engine.__init__`'s type hint, and `main.py`'s `_on_action` definition. `click_log.record`/`click_feedback.show_pulse`'s signatures match between their Task 4/5 definitions, their tests, and Task 6's `main.py` call sites.
- **Runnable after every task:** Task 1 is a pure test refactor. Task 2 changes `MouseController`'s public surface (`reanchor()` already took no args before this plan; `move_cursor` signature is untouched) without touching any caller. Task 3 only adds a property and renames a private poll function plus its single call site, both in the same task. Tasks 4-5 add unimported modules. Task 6 is the only task that wires new modules into `main.py`.
- **Out of scope, confirmed absent from every task:** blocking gesture evaluation while yielded, configurable pulse appearance, structured log formats, reading the clicked UI element via UI Automation, and an in-app log viewer.
