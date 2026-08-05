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
from .tracker import FaceMetrics, FaceTracker


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
            ok, frame = self._camera.read()
            if not ok:
                time.sleep(0.05)
                continue

            frame, metrics = self._tracker.process(frame)
            self.state.update(frame, metrics)

            if metrics is None:
                self.no_face.set()
                continue
            self.no_face.clear()

            if self.control_enabled.is_set() and not self.paused.is_set():
                self._mouse_controller.move_cursor(metrics)
                for gesture_name in self._gesture_engine.evaluate(metrics):
                    self._mouse_controller.fire_action(gesture_name)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._tracker:
            self._tracker.close()
        if self._camera:
            self._camera.release()
