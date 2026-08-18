"""Renders the config window's live preview frame: resize, draw the
head-anchor overlay from MediaPipe metrics (same overlay the old Tkinter
config window drew), encode to JPEG bytes ready for base64 over the IPC
protocol. Electron never receives raw landmarks."""
from __future__ import annotations

import cv2

from .tracker import EYE_OUTER_A, EYE_OUTER_B, GESTURE_LANDMARK_GROUPS, FaceMetrics

PREVIEW_SIZE = (480, 360)
JPEG_QUALITY = 80

HIGHLIGHT_COLOR_BGR = (0, 255, 0)
HIGHLIGHT_FILL_ALPHA = 0.35
# Landmark groups hug the feature tightly (e.g. just the eye corners/lids),
# so the zone is padded outward -- both a fraction of the group's own size
# and a fixed minimum -- to read as "this area of the face" rather than a
# box drawn exactly on the eyelid.
HIGHLIGHT_PADDING_FRACTION = 0.4
HIGHLIGHT_PADDING_MIN_PX = 10


def render_preview_jpeg(
    frame, metrics: FaceMetrics | None, highlighted_gesture: str | None = None
) -> bytes:
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
        _draw_gesture_highlight(display, metrics, highlighted_gesture, width, height)
    ok, buffer = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("failed to encode preview frame as JPEG")
    return buffer.tobytes()


def _draw_gesture_highlight(
    display, metrics: FaceMetrics, highlighted_gesture: str | None, width: int, height: int
) -> None:
    indices = GESTURE_LANDMARK_GROUPS.get(highlighted_gesture) if highlighted_gesture else None
    if not indices:
        return

    xs = [metrics.landmarks[i][0] * width for i in indices]
    ys = [metrics.landmarks[i][1] * height for i in indices]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    pad_x = max((x_max - x_min) * HIGHLIGHT_PADDING_FRACTION, HIGHLIGHT_PADDING_MIN_PX)
    pad_y = max((y_max - y_min) * HIGHLIGHT_PADDING_FRACTION, HIGHLIGHT_PADDING_MIN_PX)
    center = (int((x_min + x_max) / 2), int((y_min + y_max) / 2))
    axes = (int((x_max - x_min) / 2 + pad_x), int((y_max - y_min) / 2 + pad_y))

    overlay = display.copy()
    cv2.ellipse(overlay, center, axes, 0, 0, 360, HIGHLIGHT_COLOR_BGR, -1)
    cv2.addWeighted(overlay, HIGHLIGHT_FILL_ALPHA, display, 1 - HIGHLIGHT_FILL_ALPHA, 0, display)
    cv2.ellipse(display, center, axes, 0, 0, 360, HIGHLIGHT_COLOR_BGR, 2)
