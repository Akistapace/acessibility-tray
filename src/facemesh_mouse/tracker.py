"""Wraps MediaPipe FaceMesh: raw camera frame -> normalized face metrics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import mediapipe as mp

# Canonical FaceMesh landmark indices used throughout the project.
# Nose tip / chin / forehead-top follow the classic 6-point head-pose set
# used in most MediaPipe head-pose tutorials.
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

# 6-point EAR (Soukupova & Cech) landmark sets, in
# [outer_corner, top1, top2, inner_corner, bottom2, bottom1] order.
# Labels "left"/"right" are an internal convention only (see README) --
# use the config GUI's live preview to see which indicator reacts to which
# physical eye and map gestures accordingly.
EYE_A = [33, 160, 158, 133, 153, 144]
EYE_B = [362, 385, 387, 263, 373, 380]

MOUTH_TOP_INNER = 13
MOUTH_BOTTOM_INNER = 14
MOUTH_CORNER_LEFT = 61
MOUTH_CORNER_RIGHT = 291

EYEBROW_A = 105
EYEBROW_B = 334
EYELID_TOP_A = 159
EYELID_TOP_B = 386


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


def _dist(p1, p2) -> float:
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def _eye_aspect_ratio(pts: list) -> float:
    p1, p2, p3, p4, p5, p6 = pts
    vertical = _dist(p2, p6) + _dist(p3, p5)
    horizontal = 2.0 * _dist(p1, p4)
    if horizontal == 0:
        return 0.0
    return vertical / horizontal


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


class FaceTracker:
    """Stateful MediaPipe FaceMesh wrapper. One instance per camera stream."""

    def __init__(self) -> None:
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def process(self, frame_bgr) -> tuple:
        """Mirrors the frame for natural on-screen orientation, runs FaceMesh.

        Returns (mirrored_frame_bgr, FaceMetrics | None). Metrics is None
        when no face is detected in the frame.
        """
        frame_bgr = cv2.flip(frame_bgr, 1)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._mesh.process(rgb)

        if not result.multi_face_landmarks:
            return frame_bgr, None

        lm = result.multi_face_landmarks[0].landmark
        pts = [(p.x, p.y) for p in lm]

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

    def close(self) -> None:
        self._mesh.close()
