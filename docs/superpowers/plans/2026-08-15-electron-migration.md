# Electron Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every visual surface (config window, tray, click-feedback overlay, floating keyboard/mic buttons) with an Electron + TypeScript frontend, while the existing tracking/gesture/mouse-control engine keeps running in Python, unchanged in behavior, as a headless backend process.

**Architecture:** Electron main process owns all windows, the tray, global hotkeys, and single-instance enforcement, and spawns the Python engine as a child process. The two talk newline-delimited JSON over the child's stdin/stdout. Renderers never touch Python directly — `contextIsolation` stays on, all backend traffic is relayed through the main process.

**Tech Stack:** Python 3.11 (existing: OpenCV, MediaPipe, pynput), TypeScript, Electron, electron-builder, vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-electron-migration-design.md`

## Global Constraints

- The Python backend's `stdout` carries protocol only — every diagnostic `print`/log call must go to `stderr`, never `stdout`.
- Every Electron `BrowserWindow` uses `nodeIntegration: false`, `contextIsolation: true`. Renderers reach the backend only through the preload `contextBridge` + main-process relay.
- TypeScript, not plain JavaScript, for the entire Electron side.
- Functional 1:1 port: same tabs, same fields, same gesture set, same flow as the current Tkinter app. No new features, no visual redesign — redesign is an explicit later phase with its own spec.
- Windows-only. No cross-platform code paths.
- Packaging: `electron-builder` with an `nsis` target; the Python backend is frozen with `pyinstaller --onefile` and bundled as `extraResources`.

---

## Part 1 — Python backend

### Task 1: Extract `config_to_dict` / `config_from_dict`

**Files:**
- Modify: `src/facemesh_mouse/modules/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config_to_dict(config: AppConfig) -> dict`, `config_from_dict(raw: dict) -> AppConfig` — used by every later backend task that serializes config over IPC.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_config_to_dict_from_dict_round_trip():
    original = config_mod.default_config()
    original.calibration.sensitivity_x = 0.04
    original.gestures["mouth_open"].action = "scroll_down"
    original.action_buttons.x = 12.0

    restored = config_mod.config_from_dict(config_mod.config_to_dict(original))

    assert restored.calibration.sensitivity_x == 0.04
    assert restored.gestures["mouth_open"].action == "scroll_down"
    assert restored.action_buttons.x == 12.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_config.py -k round_trip -v`
Expected: FAIL — `AttributeError: module 'facemesh_mouse.modules.config' has no attribute 'config_to_dict'`

- [ ] **Step 3: Implement**

In `src/facemesh_mouse/modules/config.py`, replace the body of `load_config` from `default = default_config()` onward, and all of `save_config`, with:

```python
def config_to_dict(config: AppConfig) -> dict:
    return {
        "calibration": asdict(config.calibration),
        "gestures": {name: asdict(cfg) for name, cfg in config.gestures.items()},
        "action_buttons": asdict(config.action_buttons),
    }


def config_from_dict(raw: dict) -> AppConfig:
    default = default_config()
    # Pre-optical-flow keys (x_min, x_max, y_min, y_max, smoothing,
    # deadzone_px, sensitivity) are simply not read here, so they fall away
    # on the next save. No migration is attempted: four-point calibration
    # bounds have no sensitivity equivalent to convert to.
    raw_cal = raw.get("calibration", {})
    click_logging_enabled = raw_cal.get(
        "click_logging_enabled", default.calibration.click_logging_enabled
    )
    if not isinstance(click_logging_enabled, bool):
        click_logging_enabled = default.calibration.click_logging_enabled
    dwell_click_enabled = raw_cal.get(
        "dwell_click_enabled", default.calibration.dwell_click_enabled
    )
    if not isinstance(dwell_click_enabled, bool):
        dwell_click_enabled = default.calibration.dwell_click_enabled
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
        dwell_click_enabled=dwell_click_enabled,
        dwell_time_s=_clamped(raw_cal, "dwell_time_s", default.calibration.dwell_time_s),
    )

    raw_gestures = dict(raw.get("gestures", {}))
    for legacy_name, current_name in LEGACY_GESTURE_NAMES.items():
        if legacy_name in raw_gestures and current_name not in raw_gestures:
            raw_gestures[current_name] = raw_gestures[legacy_name]

    gestures = {
        name: _merge_gesture(name, raw_gestures.get(name, {}))
        for name in GESTURE_NAMES
    }

    raw_buttons = raw.get("action_buttons", {})
    action_buttons = ActionButtonsConfig(
        x=_optional_float(raw_buttons.get("x")),
        y=_optional_float(raw_buttons.get("y")),
    )

    return AppConfig(
        calibration=calibration,
        gestures=gestures,
        action_buttons=action_buttons,
    )


def load_config(path: str | Path) -> AppConfig:
    """Loads config from `path`, filling in defaults for missing fields.

    Falls back to a full default config if the file is missing or invalid.
    """
    path = Path(path)
    if not path.exists():
        return default_config()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return default_config()

    return config_from_dict(raw)


def save_config(path: str | Path, config: AppConfig) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config_to_dict(config), indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run the full config test suite**

Run: `.venv\Scripts\pytest tests/test_config.py -v`
Expected: PASS (all existing tests plus the new one — `load_config`/`save_config`'s behavior is unchanged, only routed through the two new functions)

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/modules/config.py tests/test_config.py
git commit -m "refactor(config): extract config_to_dict/config_from_dict for IPC reuse"
```

---

### Task 2: `ipc_protocol.py` — line-delimited JSON framing

**Files:**
- Create: `src/facemesh_mouse/modules/ipc_protocol.py`
- Test: `tests/test_ipc_protocol.py`

**Interfaces:**
- Produces: `write_message(stream, message: dict) -> None`, `read_messages(stream) -> Iterator[dict]`, `frame_message(jpeg_b64, gesture_progress, seq) -> dict`, `status_message(control_enabled, paused, no_face, yielded) -> dict`, `action_message(gesture, action, x, y) -> dict`, `keyboard_result_message(opened, x, y) -> dict`, `error_message(message) -> dict` — used by `backend.py` (Tasks 4-6).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ipc_protocol.py`:

```python
import io

from facemesh_mouse.modules import ipc_protocol as proto


def test_write_message_writes_one_json_line():
    stream = io.StringIO()
    proto.write_message(stream, {"type": "status", "paused": False})

    assert stream.getvalue() == '{"type":"status","paused":false}\n'


def test_read_messages_yields_each_line_as_a_dict():
    stream = io.StringIO('{"type":"start"}\n{"type":"stop"}\n')

    assert list(proto.read_messages(stream)) == [{"type": "start"}, {"type": "stop"}]


def test_read_messages_skips_blank_and_malformed_lines():
    stream = io.StringIO('{"type":"start"}\n\nnot json\n{"type":"stop"}\n')

    assert list(proto.read_messages(stream)) == [{"type": "start"}, {"type": "stop"}]


def test_frame_message_shape():
    msg = proto.frame_message("abc123", {"blink_a": 0.5}, seq=7)
    assert msg == {
        "type": "frame",
        "jpeg_b64": "abc123",
        "gesture_progress": {"blink_a": 0.5},
        "seq": 7,
    }


def test_status_message_shape():
    assert proto.status_message(True, False, True, False) == {
        "type": "status",
        "control_enabled": True,
        "paused": False,
        "no_face": True,
        "yielded": False,
    }


def test_action_message_shape():
    assert proto.action_message("blink_a", "left_click", 640, 480) == {
        "type": "action",
        "gesture": "blink_a",
        "action": "left_click",
        "x": 640,
        "y": 480,
    }


def test_keyboard_result_message_shape():
    assert proto.keyboard_result_message(False, 10, 20) == {
        "type": "keyboard_result",
        "opened": False,
        "x": 10,
        "y": 20,
    }


def test_error_message_shape():
    assert proto.error_message("camera") == {"type": "error", "message": "camera"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_ipc_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'facemesh_mouse.modules.ipc_protocol'`

- [ ] **Step 3: Implement**

Create `src/facemesh_mouse/modules/ipc_protocol.py`:

```python
"""Newline-delimited JSON protocol shared with the Electron frontend's
`protocol.ts`. One JSON object per line; the Python backend's stdout
carries protocol only (see backend.py's stdout redirect)."""
from __future__ import annotations

import json
from typing import Iterator, TextIO


def encode_message(message: dict) -> str:
    return json.dumps(message, separators=(",", ":")) + "\n"


def write_message(stream: TextIO, message: dict) -> None:
    stream.write(encode_message(message))
    stream.flush()


def read_messages(stream: TextIO) -> Iterator[dict]:
    """Yields one dict per well-formed line. A malformed line is skipped,
    never raised -- a single bad command must never kill the backend."""
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def frame_message(jpeg_b64: str, gesture_progress: dict, seq: int) -> dict:
    return {
        "type": "frame",
        "jpeg_b64": jpeg_b64,
        "gesture_progress": gesture_progress,
        "seq": seq,
    }


def status_message(control_enabled: bool, paused: bool, no_face: bool, yielded: bool) -> dict:
    return {
        "type": "status",
        "control_enabled": control_enabled,
        "paused": paused,
        "no_face": no_face,
        "yielded": yielded,
    }


def action_message(gesture: str, action: str, x: int, y: int) -> dict:
    return {"type": "action", "gesture": gesture, "action": action, "x": x, "y": y}


def keyboard_result_message(opened: bool, x: int, y: int) -> dict:
    return {"type": "keyboard_result", "opened": opened, "x": x, "y": y}


def error_message(message: str) -> dict:
    return {"type": "error", "message": message}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_ipc_protocol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/modules/ipc_protocol.py tests/test_ipc_protocol.py
git commit -m "feat(backend): add newline-delimited JSON IPC protocol module"
```

---

### Task 3: `preview.py` — pre-rendered JPEG preview frame

**Files:**
- Create: `src/facemesh_mouse/modules/preview.py`
- Test: `tests/test_preview.py`

**Interfaces:**
- Consumes: `FaceMetrics` from `modules/tracker.py` (`EYE_OUTER_A`, `EYE_OUTER_B` constants, `.nose_x`, `.nose_y`, `.landmarks`).
- Produces: `render_preview_jpeg(frame, metrics: FaceMetrics | None) -> bytes`, `PREVIEW_SIZE: tuple[int, int]` — used by `backend.py` Task 5.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preview.py`:

```python
import numpy as np
import cv2

from facemesh_mouse.modules import preview
from facemesh_mouse.modules.tracker import FaceMetrics


def _fake_metrics() -> FaceMetrics:
    landmarks = [(0.5, 0.5)] * 468
    landmarks[33] = (0.3, 0.5)
    landmarks[263] = (0.7, 0.5)
    return FaceMetrics(
        nose_x=0.5, nose_y=0.5, ear_a=0.3, ear_b=0.3, mouth_open_ratio=0.1,
        eyebrow_raise_a=0.1, eyebrow_raise_b=0.1, mouth_shift_ratio=0.0,
        landmarks=landmarks,
    )


def test_render_preview_jpeg_without_metrics_returns_a_decodable_jpeg():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    jpeg_bytes = preview.render_preview_jpeg(frame, None)

    decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[:2] == (preview.PREVIEW_SIZE[1], preview.PREVIEW_SIZE[0])


def test_render_preview_jpeg_with_metrics_returns_a_decodable_jpeg():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    jpeg_bytes = preview.render_preview_jpeg(frame, _fake_metrics())

    decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[:2] == (preview.PREVIEW_SIZE[1], preview.PREVIEW_SIZE[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_preview.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'facemesh_mouse.modules.preview'`

- [ ] **Step 3: Implement**

Create `src/facemesh_mouse/modules/preview.py`:

```python
"""Renders the config window's live preview frame: resize, draw the
head-anchor overlay from MediaPipe metrics (same overlay the old Tkinter
config window drew), encode to JPEG bytes ready for base64 over the IPC
protocol. Electron never receives raw landmarks."""
from __future__ import annotations

import cv2

from .tracker import EYE_OUTER_A, EYE_OUTER_B, FaceMetrics

PREVIEW_SIZE = (480, 360)
JPEG_QUALITY = 80


def render_preview_jpeg(frame, metrics: FaceMetrics | None) -> bytes:
    display = cv2.resize(frame, PREVIEW_SIZE)
    if metrics is not None:
        height, width = display.shape[:2]
        center = (int(metrics.nose_x * width), int(metrics.nose_y * height))
        left_eye = (
            int(metrics.landmarks[EYE_OUTER_A][0] * width),
            int(metrics.landmarks[EYE_OUTER_A][1] * height),
        )
        right_eye = (
            int(metrics.landmarks[EYE_OUTER_B][0] * width),
            int(metrics.landmarks[EYE_OUTER_B][1] * height),
        )
        cv2.line(display, left_eye, right_eye, (0, 255, 255), 1)
        cv2.circle(display, left_eye, 2, (0, 255, 0), -1)
        cv2.circle(display, right_eye, 2, (0, 255, 0), -1)
        cv2.circle(display, center, 5, (0, 0, 255), -1)
    ok, buffer = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("failed to encode preview frame as JPEG")
    return buffer.tobytes()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_preview.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/modules/preview.py tests/test_preview.py
git commit -m "feat(backend): add JPEG preview-frame renderer for the IPC frame push"
```

---

### Task 4: `backend.py` — `BackendServer` command dispatch

**Files:**
- Create: `src/facemesh_mouse/backend.py`
- Test: `tests/test_backend.py`

**Interfaces:**
- Consumes: `Engine` (`modules/engine.py`), `config_from_dict`/`config_to_dict`/`save_config` (Task 1), `virtual_keyboard.open_virtual_keyboard() -> bool`, `voice_typing.toggle_voice_typing() -> None`, `click_log.enable()/disable()`.
- Produces: `BackendServer(engine, config, config_path=CONFIG_PATH, send=...)`, `.handle_command(dict) -> None`, `.preview_enabled: bool`, `.config: AppConfig` — used by Tasks 5-6.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backend.py`:

```python
from facemesh_mouse import backend
from facemesh_mouse.modules import config as config_mod
from facemesh_mouse.modules.config import AppConfig
from facemesh_mouse.modules.engine import Engine


def _config_with_sensitivity(value: float) -> AppConfig:
    cfg = config_mod.default_config()
    cfg.calibration.sensitivity_x = value
    return cfg


def test_start_command_sets_control_enabled():
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config())

    server.handle_command({"type": "start"})

    assert engine.control_enabled.is_set()


def test_stop_command_clears_control_enabled():
    engine = Engine(config_mod.default_config())
    engine.control_enabled.set()
    server = backend.BackendServer(engine, config_mod.default_config())

    server.handle_command({"type": "stop"})

    assert not engine.control_enabled.is_set()


def test_pause_and_resume_commands():
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config())

    server.handle_command({"type": "pause"})
    assert engine.paused.is_set()

    server.handle_command({"type": "resume"})
    assert not engine.paused.is_set()


def test_set_preview_command_toggles_flag():
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({"type": "set_preview", "enabled": True})
    assert server.preview_enabled is True

    server.handle_command({"type": "set_preview", "enabled": False})
    assert server.preview_enabled is False


def test_update_config_command_applies_to_engine_and_updates_server_config():
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config())

    server.handle_command({
        "type": "update_config",
        "config": config_mod.config_to_dict(_config_with_sensitivity(0.09)),
    })

    assert engine._config.calibration.sensitivity_x == 0.09
    assert server.config.calibration.sensitivity_x == 0.09


def test_save_config_command_writes_to_disk(tmp_path):
    path = tmp_path / "config.json"
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config(), config_path=str(path))

    server.handle_command({
        "type": "save_config",
        "config": config_mod.config_to_dict(_config_with_sensitivity(0.07)),
    })

    assert config_mod.load_config(path).calibration.sensitivity_x == 0.07


def test_open_keyboard_command_sends_keyboard_result(monkeypatch):
    sent = []
    server = backend.BackendServer(
        Engine(config_mod.default_config()), config_mod.default_config(), send=sent.append
    )
    monkeypatch.setattr(backend.virtual_keyboard, "open_virtual_keyboard", lambda: True)

    server.handle_command({"type": "open_keyboard", "x": 100, "y": 200})

    assert sent == [{"type": "keyboard_result", "opened": True, "x": 100, "y": 200}]


def test_open_keyboard_command_reports_a_decline(monkeypatch):
    sent = []
    server = backend.BackendServer(
        Engine(config_mod.default_config()), config_mod.default_config(), send=sent.append
    )
    monkeypatch.setattr(backend.virtual_keyboard, "open_virtual_keyboard", lambda: False)

    server.handle_command({"type": "open_keyboard", "x": 5, "y": 6})

    assert sent == [{"type": "keyboard_result", "opened": False, "x": 5, "y": 6}]


def test_open_voice_typing_command_calls_toggle(monkeypatch):
    calls = []
    monkeypatch.setattr(backend.voice_typing, "toggle_voice_typing", lambda: calls.append(1))
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({"type": "open_voice_typing"})

    assert calls == [1]


def test_unknown_command_type_is_ignored():
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())
    server.handle_command({"type": "not_a_real_command"})  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_backend.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'facemesh_mouse.backend'`

- [ ] **Step 3: Implement**

Create `src/facemesh_mouse/backend.py`:

```python
"""Headless backend: wires Engine to the stdio IPC protocol (see
modules/ipc_protocol.py). BackendServer.handle_command is pure command
dispatch, testable against a real Engine with no camera or real stdio
involved -- the push loops and camera/stdin wiring live in main() (see
the design spec's Testing section: that half is manual-verified, not
unit tested, the same way it always has been for this project's
camera-dependent code paths).
"""
from __future__ import annotations

import sys
from typing import Callable

from .modules import click_log
from .modules import config as config_mod
from .modules.config import AppConfig
from .modules.engine import Engine
from .modules import ipc_protocol as proto
from . import virtual_keyboard
from . import voice_typing

CONFIG_PATH = "config.json"


class BackendServer:
    def __init__(
        self,
        engine: Engine,
        config: AppConfig,
        config_path: str = CONFIG_PATH,
        send: Callable[[dict], None] = lambda message: None,
    ) -> None:
        self._engine = engine
        self.config = config
        self._config_path = config_path
        self._send = send
        self.preview_enabled = False

    def handle_command(self, command: dict) -> None:
        handler = getattr(self, f"_cmd_{command.get('type')}", None)
        if handler is None:
            return
        handler(command)

    def _cmd_set_preview(self, command: dict) -> None:
        self.preview_enabled = bool(command.get("enabled", False))

    def _cmd_start(self, _command: dict) -> None:
        self._engine.control_enabled.set()

    def _cmd_stop(self, _command: dict) -> None:
        self._engine.control_enabled.clear()

    def _cmd_pause(self, _command: dict) -> None:
        self._engine.paused.set()

    def _cmd_resume(self, _command: dict) -> None:
        self._engine.paused.clear()

    def _cmd_update_config(self, command: dict) -> None:
        self.config = config_mod.config_from_dict(command.get("config", {}))
        self._engine.update_config(self.config)
        self._sync_click_logging(self.config)

    def _cmd_save_config(self, command: dict) -> None:
        config = config_mod.config_from_dict(command.get("config", {}))
        config_mod.save_config(self._config_path, config)

    def _cmd_open_keyboard(self, command: dict) -> None:
        x, y = command.get("x", 0), command.get("y", 0)
        opened = virtual_keyboard.open_virtual_keyboard()
        self._send(proto.keyboard_result_message(opened, x, y))

    def _cmd_open_voice_typing(self, _command: dict) -> None:
        voice_typing.toggle_voice_typing()

    def _sync_click_logging(self, config: AppConfig) -> None:
        try:
            if config.calibration.click_logging_enabled:
                click_log.enable()
            else:
                click_log.disable()
        except OSError as exc:
            print(f"facemesh-mouse: click log setup failed ({exc!r})", file=sys.stderr)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_backend.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/backend.py tests/test_backend.py
git commit -m "feat(backend): add BackendServer command dispatch"
```

---

### Task 5: `backend.py` — status snapshot and frame-encoding helpers

**Files:**
- Modify: `src/facemesh_mouse/backend.py`
- Test: `tests/test_backend.py`

**Interfaces:**
- Consumes: `trigger_progress` (`modules/gestures.py`), `render_preview_jpeg` (Task 3), `config_mod.GESTURE_NAMES`.
- Produces: `_status_snapshot(engine) -> dict`, `_encode_frame(frame, metrics, config, seq) -> dict` — used by the push loops in Task 6.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_backend.py`:

```python
import numpy as np


def test_status_snapshot_reflects_engine_flags():
    engine = Engine(config_mod.default_config())
    engine.paused.set()

    assert backend._status_snapshot(engine) == {
        "control_enabled": False,
        "paused": True,
        "no_face": False,
        "yielded": False,
    }


def test_encode_frame_produces_a_frame_message_with_progress_for_every_gesture():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    config = config_mod.default_config()

    message = backend._encode_frame(frame, None, config, seq=3)

    assert message["type"] == "frame"
    assert message["seq"] == 3
    assert set(message["gesture_progress"]) == set(config_mod.GESTURE_NAMES)
    # No face detected this frame -- every bar reads empty, matching the
    # no_face status pushed alongside it, rather than freezing at a stale
    # value from the last frame that had a face.
    assert all(v == 0.0 for v in message["gesture_progress"].values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_backend.py -k "snapshot or encode_frame" -v`
Expected: FAIL — `AttributeError: module 'facemesh_mouse.backend' has no attribute '_status_snapshot'`

- [ ] **Step 3: Implement**

In `src/facemesh_mouse/backend.py`, add these imports and functions (module-level, below the existing imports and above `class BackendServer`):

```python
import base64

from .modules.gestures import trigger_progress
from . import preview as preview_mod
```

```python
def _status_snapshot(engine: Engine) -> dict:
    mouse_controller = engine.mouse_controller
    return {
        "control_enabled": engine.control_enabled.is_set(),
        "paused": engine.paused.is_set(),
        "no_face": engine.no_face.is_set(),
        "yielded": mouse_controller.yielded if mouse_controller is not None else False,
    }


def _encode_frame(frame, metrics, config: AppConfig, seq: int) -> dict:
    jpeg_bytes = preview_mod.render_preview_jpeg(frame, metrics)
    jpeg_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    gesture_progress = {
        name: (
            trigger_progress(name, metrics, gesture_cfg.threshold)
            if metrics is not None
            else 0.0
        )
        for name, gesture_cfg in config.gestures.items()
    }
    return proto.frame_message(jpeg_b64, gesture_progress, seq)
```

(`preview` is imported as `preview_mod` to avoid shadowing the `preview` module name against any later local variable of the same name in `main()`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_backend.py -v`
Expected: PASS (all tests in the file, old and new)

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/backend.py tests/test_backend.py
git commit -m "feat(backend): add status-snapshot and frame-encoding helpers"
```

---

### Task 6: `backend.py` — push-loop threads and `main()`

**Files:**
- Modify: `src/facemesh_mouse/backend.py`

**Interfaces:**
- Consumes: everything from Tasks 2-5.
- Produces: `main()` — the process entry point Task 16's `run.py` calls, and what Electron's `resolveBackendCommand` (Task 9) spawns in dev mode.

This task is process/thread/camera wiring, not decidable logic — there is nothing here to assert against without a real webcam. It is glue, verified by the manual steps below rather than a unit test, matching the design spec's own Testing section (camera + gesture + click flow has never had automated coverage in this project).

- [ ] **Step 1: Implement**

In `src/facemesh_mouse/backend.py`, add:

```python
import ctypes
import threading

STATUS_POLL_INTERVAL_S = 0.2
FRAME_INTERVAL_S = 1 / 30


def _redirect_prints_to_stderr() -> None:
    """stdout is reserved for protocol lines -- every diagnostic print in
    this process, including ones raised deep in virtual_keyboard.py or
    voice_typing.py, must land on stderr or it corrupts the line-
    delimited JSON stream Electron is parsing."""
    sys.stdout = sys.stderr


def _primary_screen_size() -> tuple[int, int]:
    return (
        ctypes.windll.user32.GetSystemMetrics(0),
        ctypes.windll.user32.GetSystemMetrics(1),
    )


def _status_loop(engine: Engine, send: Callable[[dict], None], stop: threading.Event) -> None:
    last = None
    while not stop.is_set():
        current = _status_snapshot(engine)
        if current != last:
            send(proto.status_message(**current))
            last = current
        stop.wait(STATUS_POLL_INTERVAL_S)


def _frame_loop(
    engine: Engine, server: "BackendServer", send: Callable[[dict], None], stop: threading.Event
) -> None:
    seq = 0
    while not stop.is_set():
        if server.preview_enabled:
            frame, metrics = engine.state.snapshot()
            if frame is not None:
                send(_encode_frame(frame, metrics, server.config, seq))
                seq += 1
        stop.wait(FRAME_INTERVAL_S)


def main() -> None:
    _redirect_prints_to_stderr()
    config = config_mod.load_config(CONFIG_PATH)

    def send(message: dict) -> None:
        proto.write_message(sys.stdout, message)

    def on_action(gesture_name: str, action: str, position: tuple[int, int]) -> None:
        click_log.record(gesture_name, action, position)
        send(proto.action_message(gesture_name, action, position[0], position[1]))

    engine = Engine(config, on_action=on_action)
    server = BackendServer(engine, config, config_path=CONFIG_PATH, send=send)
    server._sync_click_logging(config)

    if not engine.open_camera():
        send(proto.error_message("camera"))
        return

    engine.start(_primary_screen_size())

    stop = threading.Event()
    threading.Thread(target=_status_loop, args=(engine, send, stop), daemon=True).start()
    threading.Thread(target=_frame_loop, args=(engine, server, send, stop), daemon=True).start()

    try:
        for command in proto.read_messages(sys.stdin):
            server.handle_command(command)
    finally:
        stop.set()
        engine.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the import graph is sound**

Run: `.venv\Scripts\python -c "from facemesh_mouse import backend"`
Expected: no output, exit code 0 (confirms no circular import or syntax error before ever touching a camera)

- [ ] **Step 3: Manual smoke test against a real camera**

Run: `.venv\Scripts\python -m facemesh_mouse.backend`

The process should hang waiting for stdin (this is correct — it's blocked in `proto.read_messages(sys.stdin)`). In a second terminal, confirm it's alive and pushing status:

```powershell
# from the repo root, a throwaway one-off check -- not saved anywhere
Get-Process python | Where-Object { $_.Path -like "*facemesh-mouse*" -or $_.MainWindowTitle -eq "" } | Select-Object Id
```

Simpler: type a command directly into the first terminal's stdin and watch stdout:

```
{"type":"start"}
```

Expected: within ~200ms, a `{"type":"status",...}` line appears on stdout with `"control_enabled":true`. Press Ctrl+C to stop; confirm the webcam light turns off (camera released cleanly).

- [ ] **Step 4: Commit**

```bash
git add src/facemesh_mouse/backend.py
git commit -m "feat(backend): add push-loop threads and the headless main() entry point"
```

---

## Part 2 — Electron frontend

### Task 7: Scaffold the Electron/TypeScript project and `protocol.ts`

**Files:**
- Create: `electron/package.json`
- Create: `electron/tsconfig.json`
- Create: `electron/tsconfig.renderer.json`
- Create: `electron/scripts/copyStaticAssets.mjs`
- Create: `electron/vitest.config.ts`
- Create: `electron/src/main/protocol.ts`
- Test: `electron/tests/protocol.test.ts`

**Interfaces:**
- Produces: `BackendMessage` union type, `encodeMessage(message) -> string`, `parseLines(chunk, leftover) -> {messages, leftover}` — used by `backendProcess.ts` (Task 8).

- [ ] **Step 1: Scaffold the project**

Create `electron/package.json`:

```json
{
  "name": "facemesh-mouse-electron",
  "version": "0.1.0",
  "private": true,
  "main": "dist/main/index.js",
  "scripts": {
    "build": "tsc -p tsconfig.json && tsc -p tsconfig.renderer.json && node scripts/copyStaticAssets.mjs",
    "dev": "npm run build && electron .",
    "test": "vitest run",
    "dist": "npm run build && electron-builder --config electron-builder.yml"
  },
  "devDependencies": {
    "@types/node": "^22.10.0",
    "electron": "^33.2.0",
    "electron-builder": "^25.1.8",
    "typescript": "^5.7.2",
    "vitest": "^2.1.8"
  }
}
```

Create `electron/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "CommonJS",
    "moduleResolution": "Node",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true
  },
  "include": ["src/main", "src/preload"]
}
```

Electron's main process and preload script run under Node, so they compile to CommonJS. The renderer windows (Tasks 11-13) run inside Chromium pages with `nodeIntegration: false` — they get **no** `require()` at all, so they need their own tsconfig compiling to native ES modules instead, loaded via `<script type="module">`. Create `electron/tsconfig.renderer.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "skipLibCheck": true,
    "lib": ["ES2022", "DOM"]
  },
  "include": ["src/renderer"]
}
```

`NodeNext` module resolution is what makes TypeScript accept (and preserve, unchanged, in the emitted JS) a relative import written as `"./toggleState.js"` even though the source file on disk is `toggleState.ts` — that `.js` extension is what the browser will actually fetch at runtime, so every renderer-to-renderer import in Tasks 11-13 is written with it.

Neither tsconfig's `include` reaches into the other's tree, so no source file is ever compiled twice under two different module systems into the same output path.

`tsc` doesn't copy non-TypeScript files, so `.html`/`.css` and (later) tray icon `.png`s need an explicit copy step. Create `electron/scripts/copyStaticAssets.mjs`:

```javascript
import { cpSync, existsSync } from "node:fs";

// HTML/CSS live alongside the renderer .ts sources and load the compiled
// .js next to them at runtime -- tsc only emits the .js, so the rest of
// the directory has to be copied into dist separately.
cpSync("src/renderer", "dist/renderer", {
  recursive: true,
  filter: (source) => !source.endsWith(".ts"),
});

// electron/assets (tray icons, added in the Tray task) doesn't exist yet
// the first few times this script runs -- skip it until it does.
if (existsSync("assets")) {
  cpSync("assets", "dist/assets", { recursive: true });
}
```

Create `electron/vitest.config.ts`:

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
```

Run: `cd electron && npm install`
Expected: `node_modules/` populated, `package-lock.json` created, exit code 0.

- [ ] **Step 2: Write the failing tests**

Create `electron/tests/protocol.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { encodeMessage, parseLines } from "../src/main/protocol";

describe("encodeMessage", () => {
  it("serializes to one newline-terminated JSON line", () => {
    expect(encodeMessage({ type: "start" })).toBe('{"type":"start"}\n');
  });
});

describe("parseLines", () => {
  it("parses complete lines and returns no leftover", () => {
    const { messages, leftover } = parseLines('{"type":"start"}\n{"type":"stop"}\n', "");
    expect(messages).toEqual([{ type: "start" }, { type: "stop" }]);
    expect(leftover).toBe("");
  });

  it("buffers a partial line across chunks", () => {
    const first = parseLines('{"type":"sta', "");
    expect(first.messages).toEqual([]);
    expect(first.leftover).toBe('{"type":"sta');

    const second = parseLines('rt"}\n', first.leftover);
    expect(second.messages).toEqual([{ type: "start" }]);
    expect(second.leftover).toBe("");
  });

  it("skips blank and malformed lines", () => {
    const { messages } = parseLines('{"type":"start"}\n\nnot json\n{"type":"stop"}\n', "");
    expect(messages).toEqual([{ type: "start" }, { type: "stop" }]);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd electron && npm test`
Expected: FAIL — cannot find module `../src/main/protocol`

- [ ] **Step 4: Implement**

Create `electron/src/main/protocol.ts`:

```typescript
// Newline-delimited JSON protocol shared with the Python backend's
// modules/ipc_protocol.py. One JSON object per line; a malformed line is
// dropped rather than thrown, matching the Python side's philosophy that
// one bad message must never kill the connection.

export interface FrameMessage {
  type: "frame";
  jpeg_b64: string;
  gesture_progress: Record<string, number>;
  seq: number;
}

export interface StatusMessage {
  type: "status";
  control_enabled: boolean;
  paused: boolean;
  no_face: boolean;
  yielded: boolean;
}

export interface ActionMessage {
  type: "action";
  gesture: string;
  action: string;
  x: number;
  y: number;
}

export interface KeyboardResultMessage {
  type: "keyboard_result";
  opened: boolean;
  x: number;
  y: number;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type BackendMessage =
  | FrameMessage
  | StatusMessage
  | ActionMessage
  | KeyboardResultMessage
  | ErrorMessage;

export function encodeMessage(message: Record<string, unknown>): string {
  return JSON.stringify(message) + "\n";
}

export function parseLines(
  chunk: string,
  leftover: string
): { messages: BackendMessage[]; leftover: string } {
  const combined = leftover + chunk;
  const lines = combined.split("\n");
  const newLeftover = lines.pop() ?? "";
  const messages: BackendMessage[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      messages.push(JSON.parse(trimmed) as BackendMessage);
    } catch {
      continue;
    }
  }
  return { messages, leftover: newLeftover };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd electron && npm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add electron/package.json electron/package-lock.json electron/tsconfig.json electron/tsconfig.renderer.json electron/scripts/copyStaticAssets.mjs electron/vitest.config.ts electron/src/main/protocol.ts electron/tests/protocol.test.ts
git commit -m "feat(electron): scaffold TS project and add the line-JSON protocol codec"
```

---

### Task 8: `backendProcess.ts` — spawn and talk to the Python backend

**Files:**
- Create: `electron/src/main/backendProcess.ts`
- Create: `electron/tests/fixtures/echoBackend.mjs`
- Test: `electron/tests/backendProcess.test.ts`

**Interfaces:**
- Consumes: `encodeMessage`, `parseLines`, `BackendMessage` (Task 7).
- Produces: `class BackendProcess extends EventEmitter` with `.start()`, `.send(message)`, `.stop()`, emits `"message"` (`BackendMessage`), `"log"` (stderr text), `"exit"` (exit code) — used by `index.ts` (Task 9) and `ipcRelay.ts` (Task 10).

- [ ] **Step 1: Write the failing test and its fixture**

Create `electron/tests/fixtures/echoBackend.mjs`:

```javascript
// Test double standing in for facemesh_mouse.backend: echoes each
// incoming command back out, prefixed, so backendProcess.test.ts can
// assert round-trip wiring without spawning Python or touching a camera.
process.stdin.setEncoding("utf8");
let buffer = "";
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  const lines = buffer.split("\n");
  buffer = lines.pop() ?? "";
  for (const line of lines) {
    if (!line.trim()) continue;
    const command = JSON.parse(line);
    process.stdout.write(JSON.stringify({ type: "echo", received: command }) + "\n");
  }
});
```

Create `electron/tests/backendProcess.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import path from "node:path";
import { BackendProcess } from "../src/main/backendProcess";

const FIXTURE = path.join(__dirname, "fixtures", "echoBackend.mjs");

describe("BackendProcess", () => {
  it("round-trips a sent command through the child's stdout", async () => {
    const proc = new BackendProcess("node", [FIXTURE]);
    const received = new Promise((resolve) => proc.once("message", resolve));

    proc.start();
    proc.send({ type: "start" });

    expect(await received).toEqual({ type: "echo", received: { type: "start" } });
    proc.stop();
  });

  it("emits exit when the child process ends", async () => {
    const proc = new BackendProcess("node", ["-e", "process.exit(0)"]);
    const exited = new Promise((resolve) => proc.once("exit", resolve));

    proc.start();

    expect(await exited).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd electron && npm test`
Expected: FAIL — cannot find module `../src/main/backendProcess`

- [ ] **Step 3: Implement**

Create `electron/src/main/backendProcess.ts`:

```typescript
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { BackendMessage, encodeMessage, parseLines } from "./protocol";

export class BackendProcess extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private leftover = "";

  constructor(
    private readonly command: string,
    private readonly args: string[]
  ) {
    super();
  }

  start(): void {
    this.child = spawn(this.command, this.args, {
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk: string) => {
      const { messages, leftover } = parseLines(chunk, this.leftover);
      this.leftover = leftover;
      for (const message of messages) {
        this.emit("message", message as BackendMessage);
      }
    });
    this.child.stderr.setEncoding("utf8");
    this.child.stderr.on("data", (chunk: string) => this.emit("log", chunk));
    this.child.on("exit", (code) => this.emit("exit", code));
  }

  send(message: Record<string, unknown>): void {
    this.child?.stdin.write(encodeMessage(message));
  }

  stop(): void {
    if (!this.child) return;
    const child = this.child;
    child.stdin.end();
    // Give the backend's own `stop`-triggered `engine.stop()` (up to a
    // 2s thread join, see backend.py Task 6) a chance to exit cleanly
    // before forcing it -- mirrors Engine.stop()'s own timeout.
    const forceKillTimer = setTimeout(() => child.kill(), 2000);
    child.once("exit", () => clearTimeout(forceKillTimer));
    this.child = null;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd electron && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add electron/src/main/backendProcess.ts electron/tests/backendProcess.test.ts electron/tests/fixtures/echoBackend.mjs
git commit -m "feat(electron): add BackendProcess to spawn and talk to the Python backend"
```

---

### Task 9: `backendCommand.ts` and a minimal `index.ts`

**Files:**
- Create: `electron/src/main/backendCommand.ts`
- Create: `electron/src/main/index.ts`
- Test: `electron/tests/backendCommand.test.ts`

**Interfaces:**
- Consumes: `BackendProcess` (Task 8).
- Produces: `resolveBackendCommand(isPackaged, resourcesPath) -> {command, args}`; `index.ts` exports `let backend: BackendProcess` — read by every window task (10-13) to attach listeners and by `ipcRelay.ts` (Task 10).

- [ ] **Step 1: Write the failing test**

Create `electron/tests/backendCommand.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import path from "node:path";
import { resolveBackendCommand } from "../src/main/backendCommand";

describe("resolveBackendCommand", () => {
  it("uses the bundled exe when packaged", () => {
    const result = resolveBackendCommand(true, "C:/App/resources");
    expect(result).toEqual({
      command: path.join("C:/App/resources", "backend", "facemesh-mouse-backend.exe"),
      args: [],
    });
  });

  it("uses the dev python module otherwise", () => {
    expect(resolveBackendCommand(false, "")).toEqual({
      command: "python",
      args: ["-m", "facemesh_mouse.backend"],
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd electron && npm test`
Expected: FAIL — cannot find module `../src/main/backendCommand`

- [ ] **Step 3: Implement**

Create `electron/src/main/backendCommand.ts`:

```typescript
import path from "node:path";

export function resolveBackendCommand(
  isPackaged: boolean,
  resourcesPath: string
): { command: string; args: string[] } {
  if (isPackaged) {
    return {
      command: path.join(resourcesPath, "backend", "facemesh-mouse-backend.exe"),
      args: [],
    };
  }
  return { command: "python", args: ["-m", "facemesh_mouse.backend"] };
}
```

Create `electron/src/main/index.ts`:

```typescript
import { app, dialog } from "electron";
import { BackendProcess } from "./backendProcess";
import { resolveBackendCommand } from "./backendCommand";

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

export let backend: BackendProcess;
let quitting = false;

app.whenReady().then(() => {
  const { command, args } = resolveBackendCommand(app.isPackaged, process.resourcesPath);
  backend = new BackendProcess(command, args);

  backend.on("message", (message: { type: string; message?: string }) => {
    if (message.type !== "error") return;
    // Today's only real error case: the camera failed to open. The
    // backend sends this once, at startup, then returns without ever
    // starting its push loops -- there is nothing left running to
    // recover, so this is fatal.
    dialog.showErrorBox(
      "FaceMesh Mouse",
      "Não foi possível acessar a webcam. Verifique se ela está conectada e se " +
        "a permissão de câmera do Windows está ativa."
    );
    app.quit();
  });

  backend.on("exit", (code) => {
    if (quitting || code === 0) return;
    // The backend died mid-session (not from our own before-quit) --
    // this failure mode doesn't exist in the old Tkinter app, where
    // engine and UI shared one process and a crash took both down
    // together silently. Here the window would otherwise sit frozen
    // with a dead backend behind it, so ask instead.
    const choice = dialog.showMessageBoxSync({
      type: "error",
      message: "FaceMesh Mouse",
      detail: `O processo de rastreamento parou inesperadamente (código ${code}).`,
      buttons: ["Reiniciar", "Sair"],
      defaultId: 0,
    });
    if (choice === 0) {
      backend.start();
    } else {
      app.quit();
    }
  });

  backend.on("log", (text: string) => console.error(`[backend] ${text}`));
  backend.start();
});

app.on("before-quit", () => {
  quitting = true;
  backend?.send({ type: "stop" });
  backend?.stop();
});

app.on("window-all-closed", () => {
  // Intentionally does not quit -- the app lives in the tray with no
  // window open most of the time, same as today's Tkinter app.
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd electron && npm test`
Expected: PASS

- [ ] **Step 5: Verify the TypeScript build**

Run: `cd electron && npm run build`
Expected: exit code 0, `electron/dist/main/index.js` and `electron/dist/main/backendCommand.js` created

- [ ] **Step 6: Commit**

```bash
git add electron/src/main/backendCommand.ts electron/src/main/index.ts electron/tests/backendCommand.test.ts
git commit -m "feat(electron): resolve and spawn the backend from the main process"
```

---

### Task 10: `ipcRelay.ts` and the preload bridge

**Files:**
- Create: `electron/src/main/ipcRelay.ts`
- Create: `electron/src/preload/index.ts`
- Modify: `electron/src/main/index.ts`
- Modify: `electron/tsconfig.json`
- Test: `electron/tests/ipcRelay.test.ts`

**Interfaces:**
- Consumes: `BackendProcess` (Task 8).
- Produces: `wireBackendRelay(backend) -> void`; preload's `window.backend.send(message)` / `window.backend.on(type, callback) -> unsubscribe` — used by every renderer (Tasks 11-13).

- [ ] **Step 1: Write the failing test**

Create `electron/tests/ipcRelay.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest";
import { EventEmitter } from "node:events";

const sendMock = vi.fn();
const getAllWindowsMock = vi.fn(() => [{ webContents: { send: sendMock } }]);
const onMock = vi.fn();

vi.mock("electron", () => ({
  ipcMain: { on: onMock },
  BrowserWindow: { getAllWindows: getAllWindowsMock },
}));

describe("wireBackendRelay", () => {
  it("broadcasts backend messages to every window's webContents", async () => {
    const { wireBackendRelay } = await import("../src/main/ipcRelay");
    const backend = new EventEmitter();
    wireBackendRelay(backend as never);

    backend.emit("message", { type: "status", paused: true });

    expect(sendMock).toHaveBeenCalledWith("backend:status", { type: "status", paused: true });
  });

  it("forwards renderer commands to the backend", async () => {
    const { wireBackendRelay } = await import("../src/main/ipcRelay");
    const backend = new EventEmitter() as EventEmitter & { send: (m: unknown) => void };
    backend.send = vi.fn();
    wireBackendRelay(backend);

    const handler = onMock.mock.calls.find(([channel]) => channel === "backend:send")?.[1];
    handler(undefined, { type: "start" });

    expect(backend.send).toHaveBeenCalledWith({ type: "start" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd electron && npm test`
Expected: FAIL — cannot find module `../src/main/ipcRelay`

- [ ] **Step 3: Implement**

Create `electron/src/main/ipcRelay.ts`:

```typescript
import { BrowserWindow, ipcMain } from "electron";
import { BackendProcess } from "./backendProcess";

export function wireBackendRelay(backend: BackendProcess): void {
  backend.on("message", (message: { type: string }) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send(`backend:${message.type}`, message);
    }
  });
  ipcMain.on("backend:send", (_event, message) => {
    backend.send(message);
  });
}
```

Create `electron/src/preload/index.ts`:

```typescript
import { contextBridge, ipcRenderer, IpcRendererEvent } from "electron";

contextBridge.exposeInMainWorld("backend", {
  send: (message: Record<string, unknown>) => ipcRenderer.send("backend:send", message),
  on: (channel: string, callback: (message: unknown) => void) => {
    const listener = (_event: IpcRendererEvent, message: unknown) => callback(message);
    ipcRenderer.on(`backend:${channel}`, listener);
    return () => ipcRenderer.removeListener(`backend:${channel}`, listener);
  },
});
```

`electron/tsconfig.json`'s `include: ["src/main", "src/preload"]` (set in Task 7) already covers this file — no change needed there. Because the type is imported by name (`IpcRendererEvent`) rather than referenced through the ambient `Electron.` namespace, this file needs no DOM lib addition; it compiles under the same plain CommonJS config as the rest of the main process.

In `electron/src/main/index.ts`, wire the relay once the backend starts:

```typescript
import { wireBackendRelay } from "./ipcRelay";
```

```typescript
  backend.on("log", (text: string) => console.error(`[backend] ${text}`));
  backend.start();
  wireBackendRelay(backend);
});
```

(insert `wireBackendRelay(backend);` as the last line of the `app.whenReady().then(...)` callback, right after `backend.start();`)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd electron && npm test`
Expected: PASS

- [ ] **Step 5: Run the build**

Run: `cd electron && npm run build`
Expected: exit code 0

- [ ] **Step 6: Commit**

```bash
git add electron/src/main/ipcRelay.ts electron/src/preload/index.ts electron/src/main/index.ts electron/tsconfig.json electron/tests/ipcRelay.test.ts
git commit -m "feat(electron): relay backend messages to renderers via a typed preload bridge"
```

---

### Task 11: Config window

**Files:**
- Create: `electron/src/main/windows/configWindow.ts`
- Create: `electron/src/renderer/config/index.html`
- Create: `electron/src/renderer/config/labels.ts`
- Create: `electron/src/renderer/config/toggleState.ts`
- Create: `electron/src/renderer/config/index.ts`
- Create: `electron/src/renderer/config/style.css`
- Modify: `electron/src/main/index.ts`
- Test: `electron/tests/toggleState.test.ts`

**Interfaces:**
- Consumes: `StatusMessage`, `FrameMessage` (Task 7); `window.backend` (Task 10).
- Produces: `computeToggleState(status) -> {label, nextCommand}`; `showConfigWindow()` / exported from `configWindow.ts`, called by the tray and global shortcuts (Task 14).

This is the direct replacement for `config_gui.py` + `calibration_panel.py` + `gesture_panel.py`: one window, a preview + toggle/save on the left, three tabs (Movimento/Gestos/Ajuda) on the right, functionally identical to today's layout.

- [ ] **Step 1: Write the failing test for the toggle-button state machine**

This ports `config_gui.py`'s `_update_toggle` three-state logic (stopped / paused / active) — the one piece of this window with real decidable behavior.

Create `electron/tests/toggleState.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { computeToggleState } from "../src/renderer/config/toggleState";

const STOPPED = { control_enabled: false, paused: false, no_face: false, yielded: false };
const PAUSED = { control_enabled: true, paused: true, no_face: false, yielded: false };
const ACTIVE = { control_enabled: true, paused: false, no_face: false, yielded: false };

describe("computeToggleState", () => {
  it("shows Iniciar when control is stopped", () => {
    expect(computeToggleState(STOPPED)).toEqual({
      statusText: "Controle parado",
      buttonText: "Iniciar controle do mouse",
      nextCommand: "start",
    });
  });

  it("shows Retomar when paused", () => {
    expect(computeToggleState(PAUSED)).toEqual({
      statusText: "Controle pausado",
      buttonText: "Retomar controle do mouse",
      nextCommand: "resume",
    });
  });

  it("shows Parar when active", () => {
    expect(computeToggleState(ACTIVE)).toEqual({
      statusText: "Controle ativo",
      buttonText: "Parar controle do mouse",
      nextCommand: "stop",
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd electron && npm test`
Expected: FAIL — cannot find module `../src/renderer/config/toggleState`

- [ ] **Step 3: Implement `toggleState.ts`**

Create `electron/src/renderer/config/toggleState.ts`:

```typescript
export interface ToggleStatus {
  control_enabled: boolean;
  paused: boolean;
}

export interface ToggleState {
  statusText: string;
  buttonText: string;
  nextCommand: "start" | "resume" | "stop";
}

export function computeToggleState(status: ToggleStatus): ToggleState {
  if (!status.control_enabled) {
    return {
      statusText: "Controle parado",
      buttonText: "Iniciar controle do mouse",
      nextCommand: "start",
    };
  }
  if (status.paused) {
    return {
      statusText: "Controle pausado",
      buttonText: "Retomar controle do mouse",
      nextCommand: "resume",
    };
  }
  return {
    statusText: "Controle ativo",
    buttonText: "Parar controle do mouse",
    nextCommand: "stop",
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd electron && npm test`
Expected: PASS

- [ ] **Step 5: Write the gesture/action label constants**

Create `electron/src/renderer/config/labels.ts` (ported verbatim from `gesture_panel.py`'s `GESTURE_LABELS`/`ACTION_LABELS`/`config.GESTURE_NAMES`):

```typescript
export const GESTURE_NAMES = [
  "blink_a",
  "blink_b",
  "blink_both",
  "eyebrow_a",
  "eyebrow_b",
  "eyebrow_both",
  "mouth_open",
  "mouth_left",
  "mouth_right",
] as const;

export const GESTURE_LABELS: Record<string, string> = {
  blink_a: "Piscar olho esquerdo",
  blink_b: "Piscar olho direito",
  blink_both: "Piscar os dois olhos",
  eyebrow_a: "Sobrancelha esquerda",
  eyebrow_b: "Sobrancelha direita",
  eyebrow_both: "As duas sobrancelhas",
  mouth_open: "Boca aberta",
  mouth_left: "Boca fechada p/ esquerda",
  mouth_right: "Boca fechada p/ direita",
};

export const ACTION_LABELS: Record<string, string> = {
  none: "(nenhuma)",
  left_click: "Clique esquerdo",
  right_click: "Clique direito",
  double_click: "Duplo clique",
  scroll_up: "Scroll cima",
  scroll_down: "Scroll baixo",
  left_drag: "Clicar e arrastar (segurar)",
  freeze_cursor: "Congelar cursor (alternar)",
};
```

- [ ] **Step 6: Write the HTML shell**

Create `electron/src/renderer/config/index.html`:

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <title>FaceMesh Mouse</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div class="layout">
    <div class="left">
      <img id="preview" width="480" height="360" alt="Prévia da câmera" />
      <div id="status-label" class="status-label"></div>
      <button id="toggle-button" class="toggle-button"></button>
      <button id="save-button" class="secondary-button">Salvar configurações</button>
      <button id="reset-position-button" class="secondary-button">
        Redefinir posição do teclado/microfone
      </button>
      <p class="hint">
        Iniciar aplica os ajustes ao controle, mas só fica salvo pra próxima vez
        que você clicar em Salvar. Fechar esta janela não muda o controle nem salva.
      </p>
    </div>
    <div class="right">
      <div class="tabs">
        <button class="tab-button active" data-tab="movimento">Movimento</button>
        <button class="tab-button" data-tab="gestos">Gestos</button>
        <button class="tab-button" data-tab="ajuda">Ajuda</button>
      </div>
      <div id="tab-movimento" class="tab-panel active">
        <label>Sensibilidade horizontal
          <input type="range" id="sensitivity_x" min="0.005" max="0.10" step="0.001" />
        </label>
        <label>Sensibilidade vertical
          <input type="range" id="sensitivity_y" min="0.005" max="0.10" step="0.001" />
        </label>
        <label>Aceleração
          <input type="range" id="acceleration" min="0" max="1" step="0.01" />
        </label>
        <label>Limiar de movimento (px)
          <input type="range" id="motion_threshold_px" min="0" max="10" step="0.1" />
        </label>
        <label>Espera antes de retomar (s)
          <input type="range" id="yield_resume_after_s" min="1" max="10" step="0.1" />
        </label>
        <label><input type="checkbox" id="dwell_click_enabled" /> Clique por permanência</label>
        <label>Tempo de permanência (s)
          <input type="range" id="dwell_time_s" min="0.3" max="5" step="0.1" />
        </label>
        <label><input type="checkbox" id="click_logging_enabled" /> Registrar cliques em clicks.log</label>
      </div>
      <div id="tab-gestos" class="tab-panel">
        <div id="gesture-rows"></div>
      </div>
      <div id="tab-ajuda" class="tab-panel">
        <p>
          1. Movimento — ajuste os sliders de sensibilidade, aceleração e limiar de
          movimento. 2. Gestos — escolha a ação de cada gesto e por quanto tempo
          segurar. 3. Iniciar — a janela some e o cursor passa a seguir a cabeça.
          4. Salvar configurações — grava os ajustes atuais no arquivo.
        </p>
        <p>Ctrl+Alt+P pausa/retoma. Ctrl+Alt+O reabre esta janela.</p>
      </div>
    </div>
  </div>
  <script type="module" src="index.js"></script>
</body>
</html>
```

`copyStaticAssets.mjs` (Task 7) copies this HTML file to `dist/renderer/config/index.html`, and `tsconfig.renderer.json` compiles `index.ts` to `dist/renderer/config/index.js` right next to it — so the script tag's relative `index.js` (not `../../dist/...`) is correct once both land in the same `dist/renderer/config/` directory. It's loaded as `type="module"` because it uses native `import`, and `nodeIntegration: false` means there is no `require()` to fall back on.

- [ ] **Step 7: Write the renderer wiring**

Create `electron/src/renderer/config/index.ts`:

```typescript
import { computeToggleState } from "./toggleState.js";
import { GESTURE_LABELS, GESTURE_NAMES, ACTION_LABELS } from "./labels.js";

declare global {
  interface Window {
    backend: {
      send: (message: Record<string, unknown>) => void;
      on: (channel: string, callback: (message: unknown) => void) => () => void;
    };
  }
}

interface AppConfigJson {
  calibration: Record<string, number | boolean>;
  gestures: Record<string, { action: string; threshold: number; cooldown_ms: number; hold_ms: number }>;
  action_buttons: { x: number | null; y: number | null };
}

let currentConfig: AppConfigJson = {
  calibration: {
    sensitivity_x: 0.025,
    sensitivity_y: 0.05,
    acceleration: 0.5,
    motion_threshold_px: 0,
    yield_resume_after_s: 3,
    click_logging_enabled: true,
    dwell_click_enabled: false,
    dwell_time_s: 1,
  },
  gestures: {},
  action_buttons: { x: null, y: null },
};

let lastStatus = { control_enabled: false, paused: false, no_face: false, yielded: false };

const preview = document.getElementById("preview") as HTMLImageElement;
const statusLabel = document.getElementById("status-label") as HTMLDivElement;
const toggleButton = document.getElementById("toggle-button") as HTMLButtonElement;
const saveButton = document.getElementById("save-button") as HTMLButtonElement;

function renderGestureRows(): void {
  const container = document.getElementById("gesture-rows") as HTMLDivElement;
  container.innerHTML = "";
  for (const name of GESTURE_NAMES) {
    const gesture = currentConfig.gestures[name];
    if (!gesture) continue;
    const row = document.createElement("div");
    row.className = "gesture-row";
    row.innerHTML = `
      <strong>${GESTURE_LABELS[name]}</strong>
      <progress id="bar-${name}" max="1" value="0"></progress>
      <select id="action-${name}">
        ${Object.entries(ACTION_LABELS)
          .map(([value, label]) => `<option value="${value}">${label}</option>`)
          .join("")}
      </select>
      <label>Espera (ms) <input type="range" id="hold-${name}" min="0" max="1000" step="10" /></label>
    `;
    container.appendChild(row);
    (row.querySelector(`#action-${name}`) as HTMLSelectElement).value = gesture.action;
    (row.querySelector(`#hold-${name}`) as HTMLInputElement).value = String(gesture.hold_ms);
  }
}

function applyConfigToForm(): void {
  for (const [id, value] of Object.entries(currentConfig.calibration)) {
    const el = document.getElementById(id) as HTMLInputElement | null;
    if (!el) continue;
    if (el.type === "checkbox") el.checked = Boolean(value);
    else el.value = String(value);
  }
  renderGestureRows();
}

function readFormIntoConfig(): void {
  for (const key of Object.keys(currentConfig.calibration)) {
    const el = document.getElementById(key) as HTMLInputElement | null;
    if (!el) continue;
    currentConfig.calibration[key] = el.type === "checkbox" ? el.checked : Number(el.value);
  }
  for (const name of GESTURE_NAMES) {
    const actionEl = document.getElementById(`action-${name}`) as HTMLSelectElement | null;
    const holdEl = document.getElementById(`hold-${name}`) as HTMLInputElement | null;
    if (!actionEl || !holdEl || !currentConfig.gestures[name]) continue;
    currentConfig.gestures[name].action = actionEl.value;
    currentConfig.gestures[name].hold_ms = Number(holdEl.value);
  }
}

function updateToggleButton(): void {
  const state = computeToggleState(lastStatus);
  statusLabel.textContent = state.statusText;
  toggleButton.textContent = state.buttonText;
}

toggleButton.addEventListener("click", () => {
  readFormIntoConfig();
  const state = computeToggleState(lastStatus);
  window.backend.send({ type: "update_config", config: currentConfig });
  window.backend.send({ type: state.nextCommand });
});

saveButton.addEventListener("click", () => {
  readFormIntoConfig();
  window.backend.send({ type: "save_config", config: currentConfig });
});

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(`tab-${(button as HTMLElement).dataset.tab}`)?.classList.add("active");
  });
});

window.backend.on("status", (message) => {
  lastStatus = message as typeof lastStatus;
  updateToggleButton();
});

window.backend.on("frame", (message) => {
  const frame = message as { jpeg_b64: string; gesture_progress: Record<string, number> };
  preview.src = `data:image/jpeg;base64,${frame.jpeg_b64}`;
  for (const [name, value] of Object.entries(frame.gesture_progress)) {
    const bar = document.getElementById(`bar-${name}`) as HTMLProgressElement | null;
    if (bar) bar.value = value;
  }
});

applyConfigToForm();
updateToggleButton();
```

(`currentConfig.gestures` starts empty and gets populated the first time the main process sends the loaded config down — wired in Step 8 below.)

- [ ] **Step 8: Write `configWindow.ts`**

Create `electron/src/main/windows/configWindow.ts`:

```typescript
import { BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { BackendProcess } from "../backendProcess";

let win: BrowserWindow | null = null;

export function createConfigWindow(backend: BackendProcess): BrowserWindow {
  win = new BrowserWindow({
    width: 1060,
    height: 680,
    minWidth: 1000,
    minHeight: 620,
    title: "FaceMesh Mouse",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "config", "index.html"));
  win.on("show", () => backend.send({ type: "set_preview", enabled: true }));
  win.on("hide", () => backend.send({ type: "set_preview", enabled: false }));
  win.on("close", (event) => {
    event.preventDefault();
    win?.hide();
  });
  return win;
}

export function showConfigWindow(): void {
  win?.show();
  win?.focus();
}

ipcMain.on("config:reset-position", () => {
  // Wired to the floating-buttons window in Task 13.
});
```

- [ ] **Step 9: Wire into `index.ts`**

In `electron/src/main/index.ts`, add:

```typescript
import { createConfigWindow, showConfigWindow } from "./windows/configWindow";
```

```typescript
  backend.start();
  wireBackendRelay(backend);
  createConfigWindow(backend);
});

export { showConfigWindow };
```

(replace the closing `});` of the `app.whenReady().then(...)` block with the three lines above, and add the re-export at module scope after it)

- [ ] **Step 10: Add a minimal `style.css`**

Create `electron/src/renderer/config/style.css`:

```css
body { background: #1f1f1f; color: #e6e6e6; font-family: "Segoe UI", sans-serif; margin: 0; }
.layout { display: flex; height: 100vh; }
.left { width: 280px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.right { flex: 1; padding: 12px; overflow-y: auto; }
#preview { background: #000; border-radius: 4px; }
.toggle-button { height: 44px; font-weight: bold; }
.secondary-button { height: 36px; background: transparent; border: 1px solid #555; color: inherit; }
.hint { color: #999; font-size: 12px; }
.tabs { display: flex; gap: 4px; margin-bottom: 12px; }
.tab-button { background: transparent; border: none; color: #999; padding: 8px 12px; cursor: pointer; }
.tab-button.active { color: #fff; border-bottom: 2px solid #4da3ff; }
.tab-panel { display: none; flex-direction: column; gap: 12px; }
.tab-panel.active { display: flex; }
.gesture-row { border: 1px solid #333; border-radius: 4px; padding: 8px; margin-bottom: 8px; }
label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
```

- [ ] **Step 11: Run tests and build**

Run: `cd electron && npm test && npm run build`
Expected: tests PASS, build exit code 0

- [ ] **Step 12: Commit**

```bash
git add electron/src/main/windows/configWindow.ts electron/src/renderer/config electron/src/main/index.ts electron/tests/toggleState.test.ts
git commit -m "feat(electron): add the config window (Movimento/Gestos/Ajuda)"
```

---

### Task 12: Click-feedback overlay window

**Files:**
- Create: `electron/src/main/windows/overlayWindow.ts`
- Create: `electron/src/renderer/overlay/index.html`
- Create: `electron/src/renderer/overlay/pulse.ts`
- Create: `electron/src/renderer/overlay/index.ts`
- Modify: `electron/src/main/index.ts`
- Test: `electron/tests/pulse.test.ts`

**Interfaces:**
- Consumes: `ActionMessage`, `KeyboardResultMessage` (Task 7).
- Produces: `pulseRadius(progress, startRadius, endRadius) -> number` (ported from `click_feedback.py`'s `_START_RADIUS`/`_END_RADIUS` interpolation); `createOverlayWindow()`.

- [ ] **Step 1: Write the failing test**

Create `electron/tests/pulse.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { pulseRadius } from "../src/renderer/overlay/pulse";

describe("pulseRadius", () => {
  it("starts at the start radius", () => {
    expect(pulseRadius(0, 6, 28)).toBe(6);
  });

  it("ends at the end radius", () => {
    expect(pulseRadius(1, 6, 28)).toBe(28);
  });

  it("interpolates linearly at the midpoint", () => {
    expect(pulseRadius(0.5, 6, 28)).toBe(17);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd electron && npm test`
Expected: FAIL — cannot find module `../src/renderer/overlay/pulse`

- [ ] **Step 3: Implement `pulse.ts`**

Create `electron/src/renderer/overlay/pulse.ts`:

```typescript
// Same expanding-ring interpolation as click_feedback.py's show_pulse:
// radius grows linearly from startRadius to endRadius as progress goes
// from 0 to 1.
export function pulseRadius(progress: number, startRadius: number, endRadius: number): number {
  return startRadius + (endRadius - startRadius) * progress;
}

export const RING_COLOR = "#4da3ff";
export const WARNING_COLOR = "#ff4d4d";
export const START_RADIUS = 6;
export const END_RADIUS = 28;
export const DURATION_MS = 300;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd electron && npm test`
Expected: PASS

- [ ] **Step 5: Write the overlay HTML + renderer**

Create `electron/src/renderer/overlay/index.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>overlay</title>
  <style>
    html, body { margin: 0; background: transparent; overflow: hidden; }
    canvas { position: absolute; top: 0; left: 0; }
  </style>
</head>
<body>
  <canvas id="canvas"></canvas>
  <div id="tooltip" style="position:absolute; display:none; background:#2b2b2b; color:#fff; padding:6px 10px; border-radius:4px; font-family:'Segoe UI',sans-serif; font-size:13px;"></div>
  <script type="module" src="index.js"></script>
</body>
</html>
```

(same reasoning as the config window's Step 6: `copyStaticAssets.mjs` and `tsconfig.renderer.json` both land in `dist/renderer/overlay/`, so a same-directory relative `index.js` finds the compiled script, loaded as a module since there is no `require()` here)

Create `electron/src/renderer/overlay/index.ts`:

```typescript
import { pulseRadius, RING_COLOR, WARNING_COLOR, START_RADIUS, END_RADIUS, DURATION_MS } from "./pulse.js";

declare global {
  interface Window {
    backend: {
      send: (message: Record<string, unknown>) => void;
      on: (channel: string, callback: (message: unknown) => void) => () => void;
    };
  }
}

const canvas = document.getElementById("canvas") as HTMLCanvasElement;
canvas.width = window.screen.width;
canvas.height = window.screen.height;
const ctx = canvas.getContext("2d")!;
const tooltip = document.getElementById("tooltip") as HTMLDivElement;

function drawPulse(x: number, y: number, color: string): void {
  const steps = 10;
  let index = 0;
  const timer = setInterval(() => {
    ctx.clearRect(x - END_RADIUS - 4, y - END_RADIUS - 4, (END_RADIUS + 4) * 2, (END_RADIUS + 4) * 2);
    if (index > steps) {
      clearInterval(timer);
      return;
    }
    const radius = pulseRadius(index / steps, START_RADIUS, END_RADIUS);
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.stroke();
    index += 1;
  }, DURATION_MS / steps);
}

function showTooltip(x: number, y: number, text: string): void {
  tooltip.textContent = text;
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y - 40}px`;
  tooltip.style.display = "block";
  setTimeout(() => (tooltip.style.display = "none"), 2500);
}

window.backend.on("action", (message) => {
  const action = message as { x: number; y: number };
  drawPulse(action.x, action.y, RING_COLOR);
});

window.backend.on("keyboard_result", (message) => {
  const result = message as { opened: boolean; x: number; y: number };
  if (result.opened) {
    drawPulse(result.x, result.y, RING_COLOR);
  } else {
    drawPulse(result.x, result.y, WARNING_COLOR);
    showTooltip(result.x, result.y, "Clique num campo de texto antes de abrir o teclado");
  }
});
```

- [ ] **Step 6: Write `overlayWindow.ts`**

Create `electron/src/main/windows/overlayWindow.ts`:

```typescript
import { BrowserWindow, screen } from "electron";
import path from "node:path";

export function createOverlayWindow(): BrowserWindow {
  const displays = screen.getAllDisplays();
  const minX = Math.min(...displays.map((d) => d.bounds.x));
  const minY = Math.min(...displays.map((d) => d.bounds.y));
  const maxX = Math.max(...displays.map((d) => d.bounds.x + d.bounds.width));
  const maxY = Math.max(...displays.map((d) => d.bounds.y + d.bounds.height));

  const win = new BrowserWindow({
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setIgnoreMouseEvents(true, { forward: true });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "overlay", "index.html"));
  win.showInactive();
  return win;
}
```

- [ ] **Step 7: Wire into `index.ts`**

In `electron/src/main/index.ts`:

```typescript
import { createOverlayWindow } from "./windows/overlayWindow";
```

```typescript
  createConfigWindow(backend);
  createOverlayWindow();
});
```

(replace `createConfigWindow(backend);\n});` with the two-line version above)

- [ ] **Step 8: Run tests and build**

Run: `cd electron && npm test && npm run build`
Expected: tests PASS, build exit code 0

- [ ] **Step 9: Commit**

```bash
git add electron/src/main/windows/overlayWindow.ts electron/src/renderer/overlay electron/src/main/index.ts electron/tests/pulse.test.ts
git commit -m "feat(electron): add the click-feedback overlay window"
```

---

### Task 13: Floating keyboard/mic buttons window

**Files:**
- Create: `electron/src/main/windows/buttonsWindow.ts`
- Create: `electron/src/main/windows/buttonsPosition.ts`
- Create: `electron/src/renderer/buttons/index.html`
- Create: `electron/src/renderer/buttons/clickOrDrag.ts`
- Create: `electron/src/renderer/buttons/index.ts`
- Modify: `electron/src/main/index.ts`
- Modify: `electron/src/main/ipcRelay.ts`
- Test: `electron/tests/position.test.ts`

**Interfaces:**
- Consumes: `KeyboardResultMessage` push (handled by the overlay, Task 12); `window.backend` (Task 10).
- Produces: `isClick(press, release) -> boolean` (`renderer/buttons/clickOrDrag.ts`, used by the renderer's own pointer handlers), `defaultPosition(screenW, screenH, taskbarReservedPx?) -> {x, y}` and `resolvePosition(...) -> {x, y}` (`main/windows/buttonsPosition.ts`, used by `buttonsWindow.ts` to place the OS window) — ported verbatim from `action_buttons.py`'s `is_click`/`default_position`/`resolve_position` (same test cases as `tests/test_action_buttons.py`, translated to TS).

These three functions were one file (`is_click`, `default_position`, `resolve_position`) in the Python original because Tkinter ran click-vs-drag detection and window placement in the same process. Electron splits that process in two: click-vs-drag happens in the buttons *renderer* (deciding what a pointer release means), while placement happens in the *main* process (the only place that can call `BrowserWindow.setPosition`). Splitting the file along that same line avoids a main-process file reaching into the renderer's compiled-as-ESM tree (or vice versa), which would otherwise make the shared file compile twice, once as CommonJS and once as native ESM, colliding on the same `dist/` output path.

- [ ] **Step 1: Write the failing tests**

Create `electron/tests/position.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { CLICK_DRAG_THRESHOLD_PX, isClick } from "../src/renderer/buttons/clickOrDrag";
import { WIDTH, SIZE, MARGIN, defaultPosition, resolvePosition } from "../src/main/windows/buttonsPosition";

describe("isClick", () => {
  it("is a click within the threshold on both axes", () => {
    expect(isClick({ x: 100, y: 100 }, { x: 103, y: 102 })).toBe(true);
  });

  it("is a click exactly at the threshold", () => {
    const t = CLICK_DRAG_THRESHOLD_PX;
    expect(isClick({ x: 100, y: 100 }, { x: 100 + t, y: 100 - t })).toBe(true);
  });

  it("is a drag past the threshold on either axis", () => {
    const t = CLICK_DRAG_THRESHOLD_PX;
    expect(isClick({ x: 100, y: 100 }, { x: 100 + t + 1, y: 100 })).toBe(false);
    expect(isClick({ x: 100, y: 100 }, { x: 100, y: 100 + t + 1 })).toBe(false);
  });
});

describe("defaultPosition", () => {
  it("insets from the bottom-right corner", () => {
    expect(defaultPosition(1000, 800)).toEqual({ x: 1000 - WIDTH - MARGIN, y: 800 - SIZE - MARGIN });
  });

  it("sits above a reserved taskbar", () => {
    expect(defaultPosition(1000, 800, 48)).toEqual({
      x: 1000 - WIDTH - MARGIN,
      y: 800 - SIZE - MARGIN - 48,
    });
  });
});

describe("resolvePosition", () => {
  it("uses the saved spot when it still fits", () => {
    expect(resolvePosition(50, 60, 1000, 800)).toEqual({ x: 50, y: 60 });
  });

  it("falls back to default without a saved spot", () => {
    expect(resolvePosition(null, null, 1000, 800)).toEqual(defaultPosition(1000, 800));
  });

  it("falls back when the saved spot is off a smaller screen", () => {
    expect(resolvePosition(1900, 1000, 1000, 800)).toEqual(defaultPosition(1000, 800));
  });

  it("accepts the saved spot exactly at the far edge", () => {
    const edgeX = 1000 - WIDTH;
    const edgeY = 800 - SIZE;
    expect(resolvePosition(edgeX, edgeY, 1000, 800)).toEqual({ x: edgeX, y: edgeY });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd electron && npm test`
Expected: FAIL — cannot find module `../src/renderer/buttons/clickOrDrag` (and `../src/main/windows/buttonsPosition`)

- [ ] **Step 3: Implement `clickOrDrag.ts` and `buttonsPosition.ts`**

Create `electron/src/renderer/buttons/clickOrDrag.ts` (ported from `action_buttons.py`'s `is_click`; compiles under `tsconfig.renderer.json`):

```typescript
export const CLICK_DRAG_THRESHOLD_PX = 5;

export interface Point {
  x: number;
  y: number;
}

export function isClick(press: Point, release: Point): boolean {
  return (
    Math.abs(release.x - press.x) <= CLICK_DRAG_THRESHOLD_PX &&
    Math.abs(release.y - press.y) <= CLICK_DRAG_THRESHOLD_PX
  );
}
```

Create `electron/src/main/windows/buttonsPosition.ts` (ported from `action_buttons.py`'s `default_position`/`resolve_position`; compiles under `tsconfig.json`, the main-process CommonJS config):

```typescript
export const SIZE = 60;
export const GAP = 6;
export const WIDTH = SIZE * 2 + GAP;
export const MARGIN = 24;

export interface Point {
  x: number;
  y: number;
}

export function defaultPosition(screenW: number, screenH: number, taskbarReservedPx = 0): Point {
  return { x: screenW - WIDTH - MARGIN, y: screenH - SIZE - MARGIN - taskbarReservedPx };
}

export function resolvePosition(
  savedX: number | null,
  savedY: number | null,
  screenW: number,
  screenH: number,
  taskbarReservedPx = 0
): Point {
  if (savedX === null || savedY === null) {
    return defaultPosition(screenW, screenH, taskbarReservedPx);
  }
  if (!(savedX >= 0 && savedX <= screenW - WIDTH) || !(savedY >= 0 && savedY <= screenH - SIZE)) {
    return defaultPosition(screenW, screenH, taskbarReservedPx);
  }
  return { x: savedX, y: savedY };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd electron && npm test`
Expected: PASS

- [ ] **Step 5: Write the buttons HTML + renderer**

Create `electron/src/renderer/buttons/index.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>buttons</title>
  <style>
    html, body { margin: 0; background: transparent; overflow: hidden; user-select: none; }
    .circle { position: absolute; top: 2px; width: 56px; height: 56px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center; font-size: 20px; color: #fff;
      cursor: pointer; }
    #keyboard { left: 2px; background: #4da3ff; }
    #mic { left: 66px; background: #ff6b6b; }
  </style>
</head>
<body>
  <div id="keyboard" class="circle">⌨</div>
  <div id="mic" class="circle">🎤</div>
  <script type="module" src="index.js"></script>
</body>
</html>
```

(same same-directory relative-path reasoning as the config and overlay windows — see Task 11 Step 6)

Create `electron/src/renderer/buttons/index.ts`:

```typescript
import { isClick } from "./clickOrDrag.js";

declare global {
  interface Window {
    backend: {
      send: (message: Record<string, unknown>) => void;
      on: (channel: string, callback: (message: unknown) => void) => () => void;
    };
  }
}

let press: { x: number; y: number } | null = null;

function onPointerDown(event: PointerEvent, target: "keyboard" | "mic"): void {
  press = { x: event.screenX, y: event.screenY };
  (event.target as HTMLElement).setPointerCapture(event.pointerId);
  (event.target as HTMLElement).dataset.target = target;
}

function onPointerUp(event: PointerEvent): void {
  if (!press) return;
  const release = { x: event.screenX, y: event.screenY };
  const target = (event.target as HTMLElement).dataset.target;
  if (isClick(press, release)) {
    if (target === "keyboard") {
      window.backend.send({ type: "open_keyboard", x: release.x, y: release.y });
    } else if (target === "mic") {
      window.backend.send({ type: "open_voice_typing" });
    }
  } else {
    // Dragging moved the whole OS window already (see onPointerMove);
    // tell the main process the drag ended so it can persist the spot.
    window.backend.send({ type: "buttons:drag-end" });
  }
  press = null;
}

function onPointerMove(event: PointerEvent): void {
  if (!press || event.buttons !== 1) return;
  const dx = event.screenX - press.x;
  const dy = event.screenY - press.y;
  if (Math.abs(dx) > 0 || Math.abs(dy) > 0) {
    ipcMoveWindow(dx, dy);
  }
}

function ipcMoveWindow(dx: number, dy: number): void {
  window.backend.send({ type: "buttons:drag-move", dx, dy });
}

const keyboard = document.getElementById("keyboard") as HTMLDivElement;
const mic = document.getElementById("mic") as HTMLDivElement;
for (const [el, name] of [
  [keyboard, "keyboard"],
  [mic, "mic"],
] as const) {
  el.addEventListener("pointerdown", (e) => onPointerDown(e, name));
  el.addEventListener("pointerup", onPointerUp);
  el.addEventListener("pointermove", onPointerMove);
}
```

`buttons:drag-move` / `buttons:drag-end` are handled main-process-side (Step 6) rather than routed to the Python backend — the buttons window's `send` goes through the same `window.backend.send` bridge, but `buttonsWindow.ts` intercepts those two message types itself before they'd otherwise be forwarded to Python (which has no handler for them and would just ignore them harmlessly via `BackendServer`'s unknown-command no-op — see Task 4 — but intercepting keeps drag latency off the Python round-trip entirely).

- [ ] **Step 6: Write `buttonsWindow.ts`**

Create `electron/src/main/windows/buttonsWindow.ts`:

```typescript
import { BrowserWindow, ipcMain, screen } from "electron";
import path from "node:path";
import { BackendProcess } from "../backendProcess";
import { defaultPosition, resolvePosition, WIDTH, SIZE } from "./buttonsPosition";

let win: BrowserWindow | null = null;

export function createButtonsWindow(
  backend: BackendProcess,
  savedX: number | null,
  savedY: number | null
): BrowserWindow {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workArea;
  const taskbarReservedPx = screen.getPrimaryDisplay().bounds.height - screenH;
  const { x, y } = resolvePosition(savedX, savedY, screenW, screenH, taskbarReservedPx);

  win = new BrowserWindow({
    x: Math.round(x),
    y: Math.round(y),
    width: WIDTH,
    height: SIZE,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "buttons", "index.html"));
  win.showInactive();

  // These two channels are re-emitted by ipcRelay.ts (Step 7 below) rather
  // than delivered on the shared "backend:send" channel directly -- a raw
  // listener there would also see every command meant for Python (start,
  // update_config, ...) and would need to filter them back out itself.
  ipcMain.on("buttons:drag-move", (_event, message: { dx: number; dy: number }) => {
    if (!win) return;
    const [curX, curY] = win.getPosition();
    win.setPosition(curX + message.dx, curY + message.dy);
  });
  ipcMain.on("buttons:drag-end", () => {
    if (!win) return;
    const [curX, curY] = win.getPosition();
    backend.send({
      type: "save_config",
      config: { action_buttons: { x: curX, y: curY } },
    });
  });

  return win;
}

export function resetButtonsPosition(): void {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workArea;
  const taskbarReservedPx = screen.getPrimaryDisplay().bounds.height - screenH;
  const { x, y } = defaultPosition(screenW, screenH, taskbarReservedPx);
  win?.setPosition(Math.round(x), Math.round(y));
}
```

The `save_config` sent on drag-end intentionally carries only `action_buttons` — the config window's own `save_config` (Task 11) always sends the full config object it holds, so a background drag-only save here must not clobber calibration/gesture fields the config window has pending. This mirrors `action_buttons.py`'s existing `_save_position`, which does a read-modify-write against the file instead of a whole-object write for exactly this reason (see `test_dragging_does_not_clobber_settings_saved_after_startup`). **This means `BackendServer._cmd_save_config` (Task 4) must merge the partial dict onto the on-disk config rather than replace it wholesale — revisit Task 4 before wiring this up:**

- [ ] **Step 6b: Fix `_cmd_save_config` to merge partial config payloads**

In `src/facemesh_mouse/backend.py`, replace `_cmd_save_config`:

```python
    def _cmd_save_config(self, command: dict) -> None:
        on_disk = config_mod.load_config(self._config_path)
        on_disk_dict = config_mod.config_to_dict(on_disk)
        payload = command.get("config", {})
        merged = {**on_disk_dict, **payload}
        if "calibration" in payload:
            merged["calibration"] = {**on_disk_dict["calibration"], **payload["calibration"]}
        if "action_buttons" in payload:
            merged["action_buttons"] = {**on_disk_dict["action_buttons"], **payload["action_buttons"]}
        config_mod.save_config(self._config_path, config_mod.config_from_dict(merged))
```

Add to `tests/test_backend.py`:

```python
def test_save_config_command_merges_partial_payload_onto_disk(tmp_path):
    path = tmp_path / "config.json"
    config_mod.save_config(path, _config_with_sensitivity(0.09))
    engine = Engine(config_mod.default_config())
    server = backend.BackendServer(engine, config_mod.default_config(), config_path=str(path))

    server.handle_command({
        "type": "save_config",
        "config": {"action_buttons": {"x": 120.0, "y": 640.0}},
    })

    reloaded = config_mod.load_config(path)
    assert reloaded.calibration.sensitivity_x == 0.09
    assert reloaded.action_buttons.x == 120.0
    assert reloaded.action_buttons.y == 640.0
```

Run: `.venv\Scripts\pytest tests/test_backend.py -v`
Expected: PASS (this also covers the earlier `test_save_config_command_writes_to_disk`, which sends a full config and still round-trips correctly through the merge)

```bash
git add src/facemesh_mouse/backend.py tests/test_backend.py
git commit -m "fix(backend): merge partial save_config payloads instead of overwriting the file"
```

- [ ] **Step 7: Wire into `index.ts`**

In `electron/src/main/index.ts`:

```typescript
import { createButtonsWindow, resetButtonsPosition } from "./windows/buttonsWindow";
```

Add a listener for the loaded config's saved button position before creating the window — since `main`'s config load happens Python-side now, the simplest correct source for the initial saved position is the first `status`... actually `action_buttons.x/y` isn't part of `status`. Read it directly via Node before backend spawn:

```typescript
import fs from "node:fs";

function readSavedButtonsPosition(): { x: number | null; y: number | null } {
  try {
    const raw = JSON.parse(fs.readFileSync("config.json", "utf-8"));
    return { x: raw.action_buttons?.x ?? null, y: raw.action_buttons?.y ?? null };
  } catch {
    return { x: null, y: null };
  }
}
```

```typescript
  createOverlayWindow();
  const saved = readSavedButtonsPosition();
  createButtonsWindow(backend, saved.x, saved.y);
});
```

(replace `createOverlayWindow();\n});` with the three lines above)

Wire the config window's reset button (its `ipcMain.on("config:reset-position", ...)` stub from Task 11 Step 8) to actually call `resetButtonsPosition()`:

In `electron/src/main/windows/configWindow.ts`, replace:

```typescript
ipcMain.on("config:reset-position", () => {
  // Wired to the floating-buttons window in Task 13.
});
```

with:

```typescript
import { resetButtonsPosition } from "./buttonsWindow";

ipcMain.on("config:reset-position", () => {
  resetButtonsPosition();
});
```

And in `electron/src/renderer/config/index.ts`, wire the existing `#reset-position-button`:

```typescript
document.getElementById("reset-position-button")?.addEventListener("click", () => {
  window.backend.send({ type: "config:reset-position" });
});
```

Every renderer command goes through the one shared `backend:send` channel (Task 10), but `"config:reset-position"` and the buttons window's `"buttons:drag-move"`/`"buttons:drag-end"` (Step 6 above) aren't Python protocol messages at all — they're main-process-only requests that happen to reuse the same bridge. Generalize `ipcRelay.ts` (Task 10) to route by that distinction instead of special-casing one literal type: every Python protocol message name is a single lowercase word (`start`, `update_config`, ...); every main-process-only one this plan introduces is namespaced with a colon. Replace the body of `wireBackendRelay`'s `ipcMain.on` handler in `electron/src/main/ipcRelay.ts`:

```typescript
  ipcMain.on("backend:send", (_event, message: { type: string }) => {
    if (message.type.includes(":")) {
      // Namespaced types (config:*, buttons:*) are main-process-only --
      // re-emit on ipcMain itself so the window module that owns that
      // namespace (configWindow.ts, buttonsWindow.ts) can listen for it
      // directly, instead of every listener filtering the shared channel.
      ipcMain.emit(message.type, undefined, message);
      return;
    }
    backend.send(message);
  });
```

- [ ] **Step 8: Run tests and build**

Run: `cd electron && npm test && npm run build`
Expected: tests PASS, build exit code 0

- [ ] **Step 9: Commit**

```bash
git add electron/src/main/windows/buttonsWindow.ts electron/src/main/windows/buttonsPosition.ts electron/src/renderer/buttons electron/src/main/index.ts electron/src/main/windows/configWindow.ts electron/src/renderer/config/index.ts electron/src/main/ipcRelay.ts electron/tests/position.test.ts
git commit -m "feat(electron): add the floating keyboard/mic buttons window"
```

---

### Task 14: Tray and global hotkeys

**Files:**
- Create: `electron/src/main/tray.ts`
- Modify: `electron/src/main/index.ts`
- Test: `electron/tests/trayState.test.ts`

**Interfaces:**
- Consumes: `StatusMessage` (Task 7).
- Produces: `computeTrayState(status) -> {icon, title}` (ports `tray.py`'s precedence: paused > yielded > no_face > running); `createTray(backend)`.

- [ ] **Step 1: Write the failing test**

Create `electron/tests/trayState.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { computeTrayState } from "../src/main/trayState";

describe("computeTrayState", () => {
  it("paused overrides everything else", () => {
    expect(
      computeTrayState({ control_enabled: true, paused: true, no_face: true, yielded: true })
    ).toEqual({ icon: "paused", title: "FaceMesh Mouse -- Pausado" });
  });

  it("yielded overrides no-face and running", () => {
    expect(
      computeTrayState({ control_enabled: true, paused: false, no_face: true, yielded: true })
    ).toEqual({ icon: "yielded", title: "FaceMesh Mouse -- Controle pelo mouse físico" });
  });

  it("no-face overrides running", () => {
    expect(
      computeTrayState({ control_enabled: true, paused: false, no_face: true, yielded: false })
    ).toEqual({ icon: "no_face", title: "FaceMesh Mouse -- Rosto não detectado" });
  });

  it("running when nothing else applies", () => {
    expect(
      computeTrayState({ control_enabled: true, paused: false, no_face: false, yielded: false })
    ).toEqual({ icon: "running", title: "FaceMesh Mouse" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd electron && npm test`
Expected: FAIL — cannot find module `../src/main/trayState`

- [ ] **Step 3: Implement `trayState.ts`**

Create `electron/src/main/trayState.ts`:

```typescript
export interface TrayStatus {
  control_enabled: boolean;
  paused: boolean;
  no_face: boolean;
  yielded: boolean;
}

export type TrayIconState = "running" | "paused" | "no_face" | "yielded";

export function computeTrayState(status: TrayStatus): { icon: TrayIconState; title: string } {
  if (status.paused) {
    return { icon: "paused", title: "FaceMesh Mouse -- Pausado" };
  }
  if (status.yielded) {
    return { icon: "yielded", title: "FaceMesh Mouse -- Controle pelo mouse físico" };
  }
  if (status.no_face) {
    return { icon: "no_face", title: "FaceMesh Mouse -- Rosto não detectado" };
  }
  return { icon: "running", title: "FaceMesh Mouse" };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd electron && npm test`
Expected: PASS

- [ ] **Step 5: Implement `tray.ts`**

Create `electron/src/main/tray.ts`:

```typescript
import { app, globalShortcut, Menu, nativeImage, Tray } from "electron";
import path from "node:path";
import { BackendProcess } from "./backendProcess";
import { computeTrayState, TrayStatus } from "./trayState";
import { showConfigWindow } from "./windows/configWindow";

const ICON_FILES: Record<string, string> = {
  running: "tray-running.png",
  paused: "tray-paused.png",
  no_face: "tray-no-face.png",
  yielded: "tray-yielded.png",
};

let tray: Tray | null = null;
let lastStatus: TrayStatus = { control_enabled: false, paused: false, no_face: false, yielded: false };

export function createTray(backend: BackendProcess): Tray {
  const iconPath = path.join(__dirname, "..", "..", "assets", ICON_FILES.running);
  tray = new Tray(nativeImage.createFromPath(iconPath));
  tray.setToolTip("FaceMesh Mouse");

  function togglePause(): void {
    backend.send({ type: lastStatus.paused ? "resume" : "pause" });
  }

  const menu = Menu.buildFromTemplate([
    { label: "Pausar/Retomar", click: togglePause },
    { label: "Reabrir Config", click: showConfigWindow },
    { label: "Sair", click: () => app.quit() },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", showConfigWindow);

  backend.on("message", (message: { type: string }) => {
    if (message.type !== "status") return;
    lastStatus = message as unknown as TrayStatus;
    const state = computeTrayState(lastStatus);
    tray?.setImage(nativeImage.createFromPath(path.join(__dirname, "..", "..", "assets", ICON_FILES[state.icon])));
    tray?.setToolTip(state.title);
  });

  globalShortcut.register("Ctrl+Alt+P", togglePause);
  globalShortcut.register("Ctrl+Alt+O", showConfigWindow);

  return tray;
}
```

- [ ] **Step 6: Create the four tray icon assets**

The Tkinter tray (`tray.py`) draws these procedurally with Pillow at runtime (`_make_icon_image`); Electron's `Tray` needs real files. Generate them once with a throwaway Python one-liner (uses the same colors `tray.py` already defines) and commit the results:

```powershell
.venv\Scripts\python -c "
from PIL import Image, ImageDraw
colors = {'tray-running.png': '#2ecc71', 'tray-paused.png': '#f1c40f', 'tray-no-face.png': '#e67e22', 'tray-yielded.png': '#3498db'}
for name, color in colors.items():
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
    img.save(f'electron/assets/{name}')
"
```

Expected: four PNGs created under `electron/assets/`.

- [ ] **Step 7: Wire into `index.ts`**

In `electron/src/main/index.ts`:

```typescript
import { createTray } from "./tray";
```

```typescript
  createButtonsWindow(backend, saved.x, saved.y);
  createTray(backend);
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});
```

(replace `createButtonsWindow(backend, saved.x, saved.y);\n});` with the block above, and add `import { globalShortcut } from "electron";` — or fold it into the existing `import { app } from "electron";` line as `import { app, globalShortcut } from "electron";`)

- [ ] **Step 8: Run tests and build**

Run: `cd electron && npm test && npm run build`
Expected: tests PASS, build exit code 0

- [ ] **Step 9: Manual smoke test**

Run: `cd electron && npm run dev` (requires the Python venv active so `python -m facemesh_mouse.backend` resolves — or temporarily edit `resolveBackendCommand`'s dev branch to call `.venv\Scripts\python.exe` directly)

Expected: tray icon appears; left-click opens the config window; the four states (start control, pause via `Ctrl+Alt+P`, cover the camera for no-face, touch the physical mouse for yielded) each swap the tray icon and tooltip correctly.

- [ ] **Step 10: Commit**

```bash
git add electron/src/main/tray.ts electron/src/main/trayState.ts electron/src/main/index.ts electron/assets electron/tests/trayState.test.ts
git commit -m "feat(electron): add tray icon and global hotkeys"
```

---

### Task 15: Packaging

**Files:**
- Create: `backend.spec`
- Create: `electron/electron-builder.yml`
- Modify: `electron/package.json`

**Interfaces:** none (terminal task — produces a distributable installer, consumed by nobody downstream in this plan).

- [ ] **Step 1: Create the PyInstaller spec for the headless backend**

Create `backend.spec` at the repo root (replaces `facemesh-mouse.spec`, dropped in Task 16):

```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
datas += collect_data_files('mediapipe')
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['run.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'customtkinter', 'pystray'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='facemesh-mouse-backend',
    icon='assets/icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

(`console=True`: this exe's whole job is being driven over piped stdio by Electron's `child_process.spawn(..., { windowsHide: true })` — Task 8 already hides the console window at spawn time, so `console=True` here is about giving the process a real stdio subsystem to pipe through, not about a visible window.)

- [ ] **Step 2: Create the electron-builder config**

Create `electron/electron-builder.yml`:

```yaml
appId: com.fernando.facemeshmouse
productName: FaceMesh Mouse
directories:
  output: release
files:
  - dist/**/*
extraResources:
  - from: ../dist/facemesh-mouse-backend.exe
    to: backend/facemesh-mouse-backend.exe
win:
  target: nsis
  icon: ../assets/icon.ico
nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
```

- [ ] **Step 3: Add a repo-root build script for the two-stage build**

Modify `electron/package.json`'s `scripts` block, adding a `dist:full` entry that builds the Python backend first (from the repo root) and then runs electron-builder:

```json
    "dist": "npm run build && electron-builder --config electron-builder.yml",
    "dist:full": "cd .. && .venv\\Scripts\\pyinstaller backend.spec --distpath dist && cd electron && npm run dist"
```

(add `"dist:full"` as a new line after the existing `"dist"` line)

- [ ] **Step 4: Manual verification**

Run: `.venv\Scripts\pyinstaller backend.spec --distpath dist` from the repo root.
Expected: `dist/facemesh-mouse-backend.exe` produced, exit code 0.

Run: `cd electron && npm run dist`
Expected: `electron/release/FaceMesh Mouse Setup <version>.exe` produced, exit code 0. Install it, launch the installed app, confirm the tray icon appears and the config window opens (full end-to-end is Task 17's checklist — this step only confirms the *packaged build* launches, not every feature).

- [ ] **Step 5: Commit**

```bash
git add backend.spec electron/electron-builder.yml electron/package.json
git commit -m "build: add electron-builder + pyinstaller packaging for the backend"
```

---

## Part 3 — Cutover

### Task 16: Remove the Tkinter UI

**Files:**
- Delete: `src/facemesh_mouse/main.py`
- Delete: `src/facemesh_mouse/ui/config_gui.py`
- Delete: `src/facemesh_mouse/ui/calibration_panel.py`
- Delete: `src/facemesh_mouse/ui/gesture_panel.py`
- Delete: `src/facemesh_mouse/ui/tray.py`
- Delete: `src/facemesh_mouse/ui/click_feedback.py`
- Delete: `src/facemesh_mouse/ui/action_buttons.py`
- Delete: `src/facemesh_mouse/modules/hotkeys.py`
- Delete: `src/facemesh_mouse/modules/single_instance.py`
- Delete: `tests/test_config_gui.py`, `tests/test_click_feedback.py`, `tests/test_gestures.py`'s panel-facing cases (keep the pure gesture-logic tests), `tests/test_action_buttons.py`
- Delete: `facemesh-mouse.spec`
- Modify: `run.py`
- Modify: `requirements.txt`
- Modify: `README.md`

Every one of these Tkinter modules is now fully superseded: `main.py`/`config_gui.py`/`calibration_panel.py`/`gesture_panel.py` by the config window (Task 11), `tray.py` by `tray.ts` (Task 14), `click_feedback.py` by the overlay window (Task 12), `action_buttons.py` by the buttons window (Task 13), `hotkeys.py` by `globalShortcut` (Task 14), `single_instance.py` by `app.requestSingleInstanceLock()` (Task 9).

- [ ] **Step 1: Delete the superseded modules**

```bash
git rm src/facemesh_mouse/main.py
git rm src/facemesh_mouse/ui/config_gui.py
git rm src/facemesh_mouse/ui/calibration_panel.py
git rm src/facemesh_mouse/ui/gesture_panel.py
git rm src/facemesh_mouse/ui/tray.py
git rm src/facemesh_mouse/ui/click_feedback.py
git rm src/facemesh_mouse/ui/action_buttons.py
git rm src/facemesh_mouse/modules/hotkeys.py
git rm src/facemesh_mouse/modules/single_instance.py
git rm facemesh-mouse.spec
```

- [ ] **Step 2: Delete their tests**

```bash
git rm tests/test_config_gui.py
git rm tests/test_click_feedback.py
git rm tests/test_action_buttons.py
```

Check `tests/test_gestures.py` for any test importing from `facemesh_mouse.ui` (panel-facing tests) — `trigger_progress` itself stays in `modules/gestures.py` and its tests stay; only tests that import `gesture_panel` move. Run:

Run: `Select-String -Path tests/test_gestures.py -Pattern "ui\\.gesture_panel|GesturePanel"`
Expected: no matches (the design spec already notes `trigger_progress`'s tests are pure-logic and unaffected — if this search finds something, remove just that test function, not the file)

- [ ] **Step 3: Update `run.py`**

Replace the contents of `run.py`:

```python
"""Launcher used both for `python run.py` (dev) and as the PyInstaller
entry point for the headless backend Electron spawns."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from facemesh_mouse.backend import main  # noqa: E402

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Trim now-unused dependencies**

In `requirements.txt`, remove `pystray` and `customtkinter` (no longer imported anywhere); keep `pynput` (still used by `voice_typing.py`'s `Controller`), `opencv-contrib-python`, `mediapipe`, `Pillow` (used by Task 14's icon-generation one-liner and still available if needed), `numpy<2`.

```
opencv-contrib-python==4.11.0.86
mediapipe==0.10.21
pynput
Pillow
numpy<2
```

- [ ] **Step 5: Run the full Python test suite**

Run: `.venv\Scripts\pip install -r requirements-dev.txt` (picks up the trimmed `requirements.txt`)
Run: `.venv\Scripts\pytest -v`
Expected: PASS — every remaining test (config, ipc_protocol, preview, backend, gestures, mouse_controller, tracker, point_tracker, click_log, virtual_keyboard, voice_typing) passes; no import errors from the deleted modules.

- [ ] **Step 6: Update the README**

Rewrite `README.md`'s "Setup" and "Rodar" sections to describe the two-process dev flow instead of `python run.py` launching a window directly:

```markdown
## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
cd electron
npm install
```

## Rodar (dev)

Duas partes, cada uma no seu terminal:

```powershell
# Terminal 1: backend Python (headless)
.venv\Scripts\python run.py
```

```powershell
# Terminal 2: Electron
cd electron
npm run dev
```

O Electron abre a janela de configuração automaticamente na primeira execução.
```

(keep the rest of the README's usage description — Movimento/Gestos/Ajuda, atalhos, etc. — unchanged, since the UX itself didn't change, only what launches it)

- [ ] **Step 7: Commit**

```bash
git add run.py requirements.txt README.md
git commit -m "chore: remove the Tkinter UI, now fully replaced by the Electron frontend"
```

---

### Task 17: End-to-end manual verification

**Files:** none — this task is the final acceptance check, not a code change.

- [ ] **Step 1: Full cold start**

Delete `config.json` if present. Run the backend (`​.venv\Scripts\python run.py`) then Electron (`cd electron && npm run dev`).
Expected: config window opens automatically (no saved config yet — mirrors today's first-run behavior), camera preview appears within ~1s, moving your head does not yet move the cursor (control not started).

- [ ] **Step 2: Movimento tab**

Adjust each slider (sensitivity x/y, acceleration, motion threshold, yield resume, dwell time) and toggle both checkboxes.
Expected: values persist in the form; nothing is written to `config.json` yet (only "Salvar configurações" writes).

- [ ] **Step 3: Gestos tab**

For each of the 9 gesture rows, perform the expression in front of the camera.
Expected: that row's bar fills toward 1.0 as you approach the trigger threshold; a structurally-blocked gesture (e.g. `blink_a` while both eyes are shut) reads 0.0 rather than a misleading full bar.

- [ ] **Step 4: Start / pause / stop**

Click "Iniciar controle do mouse". Expected: window hides, head movement now drives the cursor, tray icon is present.
Press `Ctrl+Alt+P`. Expected: cursor freezes, tray icon/tooltip switches to paused, tray menu label flips to "Retomar".
Press `Ctrl+Alt+P` again. Expected: cursor resumes from the same position, no jump.
Press `Ctrl+Alt+O`. Expected: config window reopens, toggle button reads "Parar controle do mouse".
Click it. Expected: control stops; tray no longer shows an active/paused/yielded state distinct from idle.

- [ ] **Step 5: Gesture-fired actions and the click-feedback overlay**

Start control again. Trigger each mapped gesture (default mapping: `blink_a` → left click, `blink_b` → right click, `mouth_open` → double click).
Expected: a blue expanding ring appears at the cursor position for each fire, on top of every other window, and does not intercept the very next click.

- [ ] **Step 6: No-face and yielded states**

Cover the camera. Expected: tray icon/tooltip switches to no-face; cursor stops responding to head movement.
Uncover it, then touch the physical mouse/trackpad. Expected: tray icon/tooltip switches to yielded; head movement is ignored until you stop touching the physical mouse for the configured resume delay (default 3s).

- [ ] **Step 7: Floating keyboard/mic buttons**

Click into a text field in some other app, then click the floating keyboard circle.
Expected: Windows' touch keyboard opens; a blue pulse confirms it.
Click somewhere with no focused text field, then click the keyboard circle again.
Expected: a red warning pulse plus a tooltip reading "Clique num campo de texto antes de abrir o teclado".
Click the mic circle.
Expected: Windows' voice-typing flyout opens on the currently focused field.
Drag the button pair to a different screen corner, then restart both processes.
Expected: it reopens at the dragged position, not the default corner.
In the config window, click "Redefinir posição do teclado/microfone".
Expected: the buttons jump back to the default bottom-right corner immediately.

- [ ] **Step 8: Save and restart**

Change a few Movimento/Gestos values, click "Salvar configurações", fully quit the app (tray → Sair) and relaunch both processes.
Expected: the saved values are back; a drag-only change to the button position from Step 7, made *after* this save, must not have reverted the calibration values saved here (this is exactly what Task 13 Step 6b's merge fix protects against — re-verify it here against the real app, not just the unit test).

- [ ] **Step 9: Packaged build**

Run the installer built in Task 15 on a clean machine or user profile if available (or at minimum the same machine). Launch the installed app with no `python`/`node` on `PATH`.
Expected: it runs identically to the dev flow — the bundled backend exe launches without needing a system Python install.

- [ ] **Step 10: Record the outcome**

No commit for this task. If every expectation above held, the migration is complete — reply to the team/spec reviewer confirming Task 17 passed. If anything failed, file it as a follow-up bug against the relevant task's files rather than reopening this plan.
