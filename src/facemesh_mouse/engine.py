"""Owns the camera + FaceMesh tracking loop, running continuously on one
background thread so the camera is only ever opened once.

The config GUI and the mouse-control logic both read the same `SharedState`
snapshot instead of independently touching the camera, which avoids two
consumers fighting over one `cv2.VideoCapture` device.
"""
from __future__ import annotations

import threading
import time

import cv2

from .config import AppConfig
from .gestures import GestureEngine
from .mouse_controller import MouseController
from .point_tracker import PointTracker
from .tracker import EYE_OUTER_A, EYE_OUTER_B, FaceMetrics, FaceTracker

# Landmarks seeded as tracking points: nose bridge and tip, nostrils,
# temples and cheek edges. Averaging more points cancels more tracking
# noise, and the grid pruning collapses any that converge.
#
# Rigid features only -- deliberately no mouth, eyebrow or eyelid points.
# Those move when the user performs a gesture, which would jerk the cursor
# at the exact moment they are trying to click.
_SEED_LANDMARKS = (98, 327, 168, 6, 197, 195, 5, 4, 234, 454, 127, 356, 122, 351)


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


class SharedState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.frame = None
        self.metrics: FaceMetrics | None = None

    def update(self, frame, metrics) -> None:
        with self._lock:
            self.frame = frame
            self.metrics = metrics

    def snapshot(self):
        with self._lock:
            return self.frame, self.metrics


class Engine:
    """Runs camera capture + tracking forever; drives the mouse only while
    `control_enabled` is set and `paused` is clear."""

    def __init__(self, config: AppConfig, camera_index: int = 0) -> None:
        self.state = SharedState()
        self.control_enabled = threading.Event()  # set = GUI hidden, control live
        self.paused = threading.Event()  # set = user paused via tray/hotkey
        self.no_face = threading.Event()

        self._config = config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._camera_index = camera_index
        self._camera: cv2.VideoCapture | None = None
        self._tracker: FaceTracker | None = None
        self._gesture_engine = GestureEngine(config)
        self._mouse_controller: MouseController | None = None
        self._point_tracker = PointTracker()
        self._was_active = False

    def open_camera(self) -> bool:
        self._camera = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        return self._camera.isOpened()

    def update_config(self, config: AppConfig) -> None:
        self._config = config
        self._gesture_engine.update_config(config)
        if self._mouse_controller:
            self._mouse_controller.update_config(config)

    def start(self, screen_size: tuple[int, int]) -> None:
        self._tracker = FaceTracker()
        self._mouse_controller = MouseController(self._config, screen_size)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_once()
            except Exception as exc:  # noqa: BLE001 - never let one frame end tracking
                # This thread is the only thing moving the cursor. Without
                # this guard a single bad frame kills it for the session:
                # the tray icon and window survive, the cursor just silently
                # stops forever.
                print(f"facemesh-mouse: frame failed ({exc!r}); continuing")
                self._point_tracker.reset()
                time.sleep(0.1)

    def _run_once(self) -> None:
        ok, frame = self._camera.read()
        if not ok:
            # A stale reference frame would make the next good frame look
            # like one enormous jump, which the acceleration curve then
            # amplifies into a cursor slam against the screen edge.
            self._point_tracker.reset()
            time.sleep(0.05)
            return

        frame, metrics = self._tracker.process(frame)
        self.state.update(frame, metrics)

        if metrics is None:
            self.no_face.set()
            self._was_active = False
            self._point_tracker.reset()
            return
        self.no_face.clear()

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]
        nose = (metrics.nose_x * width, metrics.nose_y * height)
        head_size = _head_size_px(metrics, width, height)
        candidates = _seed_candidates(metrics, width, height)
        self._point_tracker.update(gray, nose, head_size, candidates)

        self._drive_control(metrics)

    def _drive_control(self, metrics: FaceMetrics) -> None:
        """Drives the cursor/gestures for one frame with a face detected.
        Reanchors whenever the previous frame did not drive the cursor --
        covers startup, resume-from-pause, and face-reacquired uniformly."""
        active_now = self.control_enabled.is_set() and not self.paused.is_set()
        if active_now:
            if not self._was_active:
                self._mouse_controller.reanchor()
            self._mouse_controller.move_cursor(*self._point_tracker.get_movement())
            self._mouse_controller.evaluate_dwell()
            for gesture_name in self._gesture_engine.evaluate(metrics):
                self._mouse_controller.fire_action(gesture_name)
        self._was_active = active_now

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._tracker:
            self._tracker.close()
        if self._camera:
            self._camera.release()
