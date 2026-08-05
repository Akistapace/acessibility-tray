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
    eyebrow_raise_ratio: float
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

    def close(self) -> None:
        self._mesh.close()
