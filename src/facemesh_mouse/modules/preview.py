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
